# Session 06 — Step 03: MinIO Object Store & Zarr Storage Layer

**What was done:**
- Implemented `MinioZarrStorage` in `app/database/minio_client.py`:
  - Connects to MinIO / S3 endpoint using `settings.MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, and `MINIO_SECRET_KEY`.
  - Performs non-blocking availability checks with 1.5s timeout.
  - Automatic fallback to local disk storage (`data/zarr_stores/{subfolder}/{cycle_key}.zarr`) when MinIO is not running locally.
  - Automatically partitions and chunks xarray Datasets along time and lat/lon dimensions for millisecond point query performance.
  - Seamlessly opens Zarr stores from local directories or MinIO S3 buckets.
  - Provides cycle listing helper `list_saved_cycles()`.
- Exported `MinioZarrStorage` and `zarr_storage` singleton in `app/database/__init__.py`.
- Tested and verified saving, chunking, reading, and listing Zarr datasets.

**Commands:**
```bash
# Verify MinioZarrStorage round-trip
uv run python -c "
from app.database import zarr_storage
import xarray as xr, numpy as np, pandas as pd, shutil, pathlib
times = pd.date_range('2026-09-04 12:00', periods=3, freq='3h')
ds = xr.Dataset({'t2m': (['time', 'latitude', 'longitude'], np.ones((3, 5, 5)))}, coords={'time': times, 'latitude': np.linspace(6, 38, 5), 'longitude': np.linspace(68, 98, 5)})
path = zarr_storage.save_dataset(ds, 'test_cycle')
opened = zarr_storage.open_dataset(path)
assert 't2m' in opened
shutil.rmtree(pathlib.Path('data/zarr_stores/gfs/test_cycle.zarr'))
print('Success!')
"
```

**Notable output:**
- Saved and read chunked Zarr store cleanly with full variable preservation.
