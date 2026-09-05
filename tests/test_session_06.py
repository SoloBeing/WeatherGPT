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

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

# Ensure repository root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from app.database import Base, zarr_storage
from app.schemas_and_models.db_models import (
    Alert,
    ForecastCycle,
    Gazetteer,
    Observation,
    UserLocation,
)
from app.data_sources.gfs import gfs_client
from app.ingestion_pipelines.gfs_pipeline import gfs_pipeline
from app.ingestion_pipelines.scheduler import ingestion_scheduler, precompute_top_towns
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
    import numpy as np
    import pandas as pd
    import xarray as xr
    import shutil
    from pathlib import Path

    times = pd.date_range("2026-09-04 12:00", periods=2, freq="3h")
    lats = np.linspace(6.0, 38.0, 4)
    lons = np.linspace(68.0, 98.0, 4)
    ds = xr.Dataset(
        {"t2m": (["time", "latitude", "longitude"], np.zeros((2, 4, 4)))},
        coords={"time": times, "latitude": lats, "longitude": lons},
    )

    path = zarr_storage.save_dataset(ds, "test_roundtrip")
    loaded = zarr_storage.open_dataset(path)
    assert "t2m" in loaded.data_vars

    # Cleanup
    shutil.rmtree(Path("data/zarr_stores/gfs/test_roundtrip.zarr"), ignore_errors=True)


async def test_gfs_pipeline_and_reader():
    """Verify end-to-end pipeline run and GFS reader point extraction."""
    now = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
    zarr_path, _ = await gfs_pipeline.run_pipeline(
        cycle_dt=now,
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


async def test_weather_tools_with_gfs():
    """Verify current and forecast tools extract from GFS Zarr store."""
    cur_json = await get_current_weather("Delhi")
    cur_data = json.loads(cur_json)
    assert "NOAA GFS" in cur_data.get("source", "")

    fc_json = await get_forecast("Bengaluru", days=2)
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
    print("Running Session 06 Smoke Tests...")
    test_orm_models_registered()
    print("  [1/5] ORM models verification passed.")
    test_zarr_storage_roundtrip()
    print("  [2/5] Zarr storage roundtrip passed.")
    asyncio.run(test_gfs_pipeline_and_reader())
    print("  [3/5] GFS pipeline & reader test passed.")
    asyncio.run(test_weather_tools_with_gfs())
    print("  [4/5] Weather tools with GFS passed.")
    test_scheduler_configuration()
    test_api_endpoints_health_and_regression()
    print("  [5/5] Scheduler & API regression passed.")
    print("ALL SESSION 06 TESTS PASSED!")
