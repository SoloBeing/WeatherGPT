"""
Tests for Zarr Storage Integrity, Corruption Guardrails, and GFS Cycle Failover.

Verifies:
1. is_valid_zarr_store detection of valid vs empty/corrupted stores
2. open_dataset raising CorruptedZarrStoreError on malformed stores
3. list_saved_cycles filtering out corrupted or incomplete cycles
4. GFS reader automatically failing over to an older valid cycle when the latest is corrupted
"""

from datetime import datetime, timezone
from pathlib import Path
import shutil
import sys

import numpy as np
import pandas as pd
import pytest
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database.minio_client import (
    CorruptedZarrStoreError,
    is_valid_zarr_store,
    zarr_storage,
)
from app.data_sources.gfs import GFSClient, gfs_client
from app.pipelines.gfs_pipeline import (
    INDIA_LAT_MAX,
    INDIA_LAT_MIN,
    INDIA_LON_MAX,
    INDIA_LON_MIN,
    gfs_pipeline,
)


def test_is_valid_zarr_store(tmp_path: Path):
    """Verify is_valid_zarr_store correctly identifies valid vs invalid stores."""
    # 1. Non-existent path
    non_existent = tmp_path / "non_existent.zarr"
    assert is_valid_zarr_store(non_existent) is False

    # 2. Plain file instead of directory
    plain_file = tmp_path / "file.zarr"
    plain_file.write_text("not a dir")
    assert is_valid_zarr_store(plain_file) is False

    # 3. Empty directory
    empty_dir = tmp_path / "empty.zarr"
    empty_dir.mkdir()
    assert is_valid_zarr_store(empty_dir) is False

    # 4. Directory with unrelated files
    junk_dir = tmp_path / "junk.zarr"
    junk_dir.mkdir()
    (junk_dir / "random.txt").write_text("random content")
    assert is_valid_zarr_store(junk_dir) is False

    # 5. Directory with Zarr v3 root marker (zarr.json)
    zarr_v3_dir = tmp_path / "v3.zarr"
    zarr_v3_dir.mkdir()
    (zarr_v3_dir / "zarr.json").write_text('{"zarr_format": 3, "node_type": "group"}')
    assert is_valid_zarr_store(zarr_v3_dir) is True

    # 6. Directory with Zarr v2 root marker (.zgroup)
    zarr_v2_dir = tmp_path / "v2.zarr"
    zarr_v2_dir.mkdir()
    (zarr_v2_dir / ".zgroup").write_text('{"zarr_format": 2}')
    assert is_valid_zarr_store(zarr_v2_dir) is True


def test_open_dataset_corruption_guardrail(tmp_path: Path):
    """Verify open_dataset raises CorruptedZarrStoreError for corrupted directories."""
    corrupt_dir = tmp_path / "corrupted_forecast.zarr"
    corrupt_dir.mkdir()
    (corrupt_dir / "trash.bin").write_bytes(b"\x00\x01\x02")

    with pytest.raises(CorruptedZarrStoreError):
        zarr_storage.open_dataset(str(corrupt_dir))

    # Test non-existent path
    with pytest.raises(FileNotFoundError):
        zarr_storage.open_dataset(str(tmp_path / "does_not_exist.zarr"))


def test_list_saved_cycles_filters_corrupt():
    """Verify list_saved_cycles skips corrupted directories when validate=True."""
    gfs_dir = Path("data/zarr_stores/gfs")
    gfs_dir.mkdir(parents=True, exist_ok=True)

    fake_corrupt = gfs_dir / "gfs_99991231_18z_corrupt.zarr"
    fake_corrupt.mkdir(exist_ok=True)
    (fake_corrupt / "incomplete.tmp").write_text("incomplete write")

    try:
        # validate=True should exclude the corrupt directory
        validated_cycles = zarr_storage.list_saved_cycles(validate=True)
        assert "gfs_99991231_18z_corrupt" not in validated_cycles

        # validate=False returns all directory names
        raw_cycles = zarr_storage.list_saved_cycles(validate=False)
        assert "gfs_99991231_18z_corrupt" in raw_cycles
    finally:
        shutil.rmtree(fake_corrupt, ignore_errors=True)


async def test_gfs_client_cycle_failover():
    """Verify GFSClient skips a corrupted cycle and transparently loads the next valid cycle."""
    # Ensure a valid baseline cycle exists
    cycle_dt = datetime.now(timezone.utc).replace(hour=6, minute=0, second=0, microsecond=0)
    valid_cycle_key = f"gfs_{cycle_dt.strftime('%Y%m%d_%H')}z"
    valid_path = Path(f"data/zarr_stores/gfs/{valid_cycle_key}.zarr")

    if not valid_path.exists():
        await gfs_pipeline.run_pipeline(
            cycle_dt=cycle_dt,
            steps=[0, 3],
            force_synthetic=True,
            use_db=False,
        )

    # Inject a corrupt cycle with a newer timestamp so it sorts first in reverse-chronological order
    corrupt_future_key = "gfs_20991231_18z"
    corrupt_path = Path(f"data/zarr_stores/gfs/{corrupt_future_key}.zarr")
    corrupt_path.mkdir(parents=True, exist_ok=True)
    # Write a zarr.json so it initially passes directory listing, but has invalid array data that fails on decode
    (corrupt_path / "zarr.json").write_text('{"zarr_format": 3, "node_type": "group"}')
    (corrupt_path / "broken_array").mkdir(exist_ok=True)
    (corrupt_path / "broken_array" / "zarr.json").write_text('{"corrupted": true}')

    try:
        # GFSClient should fail over to valid_cycle_key
        client = GFSClient()
        assert client.has_data_for(28.6139, 77.2090) is True

        ds, active_key = client._get_active_dataset()
        try:
            assert active_key != corrupt_future_key
            assert active_key.startswith("gfs_")
            assert "t2m" in ds.data_vars or "temperature_c" in ds.data_vars
        finally:
            ds.close()

        # Verify current weather extraction succeeds despite the corrupt cycle
        point = await client.fetch_current(28.6139, 77.2090)
        assert point.temperature_c is not None
        assert "NOAA GFS" in point.source

    finally:
        shutil.rmtree(corrupt_path, ignore_errors=True)
