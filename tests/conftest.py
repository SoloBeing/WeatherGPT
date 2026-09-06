"""
WeatherGPT — Shared Pytest Fixtures.
"""

from datetime import datetime, timezone
import pytest

from app.pipelines.gfs_pipeline import gfs_pipeline


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
