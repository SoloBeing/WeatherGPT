"""
SQLAlchemy ORM Models — PostGIS + TimescaleDB tables.

Tables:
  - forecast_cycles:   registered GFS/ECMWF runs (model, run_time, valid_range, zarr_path)
  - alerts:            CAP alerts with PostGIS geometry column
  - user_locations:    user subscriptions with PostGIS point (for ST_Intersects matching)
  - gazetteer:         ~600k Indian place names (LGD/GeoNames) with pg_trgm index
  - observations:      station timeseries (TimescaleDB hypertable)
"""
