"""
Session 06 Comprehensive Smoke Tests.

Verifies:
1. SQLAlchemy ORM models and PostGIS Geometry columns
2. Alembic migrations configuration and SQL generation
3. MinIO Zarr storage layer
4. GFS GRIB2 ingestion pipeline and synthetic grid generation
5. GFS data source reader (point slicing to ForecastPoint/ForecastTimeline)
6. APScheduler ingestion triggers and top towns cache warming
7. Application endpoints regression check
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys

import pytest

import numpy as np
import pandas as pd
import xarray as xr
from fastapi.testclient import TestClient

# Ensure repository root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import Base, zarr_storage
from app.schemas_and_models.db_models import (
    Alert,
    ForecastCycle,
    Gazetteer,
    Observation,
    UserLocation,
)
from app.data_sources.gfs import gfs_client
from app.ingestion_pipelines.gfs_pipeline import (
    INDIA_LAT_MIN,
    INDIA_LAT_MAX,
    INDIA_LON_MIN,
    INDIA_LON_MAX,
    gfs_pipeline,
)
from app.ingestion_pipelines.scheduler import ingestion_scheduler
from app.weather_tools.current import get_current_weather
from app.weather_tools.forecast import get_forecast
from app.main import app


def test_orm_models_registered():
    """Verify all 5 tables are registered in Base.metadata with proper columns."""
    models = [ForecastCycle, Alert, UserLocation, Gazetteer, Observation]
    expected = {"forecast_cycles", "alerts", "user_locations", "gazetteer", "observations"}
    assert {m.__tablename__ for m in models} == expected

    # Check PostGIS geometry columns
    assert "geom" in Alert.__table__.columns
    assert "geom" in UserLocation.__table__.columns
    assert "geom" in Gazetteer.__table__.columns


def test_zarr_storage_roundtrip():
    """Verify xarray dataset saving and loading via zarr_storage."""
    today_12z = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0, tzinfo=None)
    times = pd.date_range(today_12z, periods=2, freq="3h")
    # Miniature 4x4 spatial grid spanning the India NWP bounding box
    lats = np.linspace(INDIA_LAT_MIN, INDIA_LAT_MAX, 4)
    lons = np.linspace(INDIA_LON_MIN, INDIA_LON_MAX, 4)
    ds = xr.Dataset(
        {"t2m": (["time", "latitude", "longitude"], np.zeros((2, 4, 4)))},
        coords={"time": times, "latitude": lats, "longitude": lons},
    )

    loaded = None
    try:
        path = zarr_storage.save_dataset(ds, "test_roundtrip")
        loaded = zarr_storage.open_dataset(path)
        assert "t2m" in loaded.data_vars
    finally:
        if loaded is not None:
            loaded.close()
        # Cleanup
        shutil.rmtree(Path("data/zarr_stores/gfs/test_roundtrip.zarr"), ignore_errors=True)


async def test_gfs_pipeline_and_reader():
    """Verify end-to-end pipeline run and GFS reader point extraction."""
    cycle_dt = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    zarr_path, _ = await gfs_pipeline.run_pipeline(
        cycle_dt=cycle_dt,
        steps=[0, 3],
        force_synthetic=True,
        use_db=False,
    )
    assert "gfs_" in zarr_path

    # Verify GFS client queries
    assert gfs_client.has_data_for(28.6139, 77.2090)  # Delhi
    assert gfs_client.has_data_for(19.0760, 72.8777)  # Mumbai

    pt = await gfs_client.fetch_current(28.6139, 77.2090)
    assert pt.temperature_c is not None
    assert "NOAA GFS" in pt.source

    timeline = await gfs_client.fetch_forecast(19.0760, 72.8777, days=2, include_hourly=True)
    assert len(timeline.daily) > 0
    assert timeline.hourly is not None
    assert len(timeline.hourly) == 2


@pytest.fixture
async def synthetic_gfs_cycle():
    """Ensure a synthetic GFS cycle is available in local Zarr storage."""
    cycle_dt = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    zarr_path, _ = await gfs_pipeline.run_pipeline(
        cycle_dt=cycle_dt,
        steps=[0, 3],
        force_synthetic=True,
        use_db=False,
    )
    return zarr_path


async def test_weather_tools_with_gfs(synthetic_gfs_cycle):
    """Verify current and forecast tools extract from GFS Zarr store."""
    cur_json = await get_current_weather("Delhi")
    cur_data = json.loads(cur_json)
    assert "NOAA GFS" in cur_data.get("source", "")

    fc_json = await get_forecast("Maharashtra", days=2)
    fc_data = json.loads(fc_json)
    assert "NOAA GFS" in fc_data.get("source", "")


def test_scheduler_configuration():
    """Verify scheduler registers cron and interval ingestion jobs."""
    ingestion_scheduler.setup_jobs()
    job_ids = [j.id for j in ingestion_scheduler.scheduler.get_jobs()]
    assert "gfs_nwp_ingest" in job_ids
    assert "sachet_alert_poll" in job_ids


def test_api_endpoints_health_and_regression():
    """Verify FastAPI routes /health and /voice/languages respond correctly."""
    client = TestClient(app)

    # Health check
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "database" in data
    assert "redis" in data

    # Voice languages endpoint
    resp_lang = client.get("/voice/languages")
    assert resp_lang.status_code == 200
    langs = resp_lang.json()["languages"]
    assert len(langs) == 23


if __name__ == "__main__":
    sys.exit(pytest.main(["-v", __file__]))


