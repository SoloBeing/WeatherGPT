"""
GFS Ingestion Pipeline — Runs on its own clock, never in the request path.

Flow (from spec):
  GFS cycle lands on S3 (00/06/12/18Z)
    → Prefect/APScheduler triggers ~3.5h after cycle time
    → herbie downloads subset (India bbox, ~12 variables)
    → cfgrib → xarray → write Zarr to MinIO
    → register cycle in Postgres (model, run_time, valid_range, path)
"""
