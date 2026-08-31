"""
GFS Reader — NOAA Global Forecast System via Zarr store.

Raw 0.25° GRIB2, 4 cycles/day (00/06/12/18Z), 384h horizon.
Source: s3://noaa-gfs-bdp-pds (anonymous access).
Ingestion pipeline writes to local Zarr (MinIO), this reads from it.
"""
