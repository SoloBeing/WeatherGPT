# schemas_and_models — Context

## Role
All type definitions in one place: Pydantic schemas (API) + SQLAlchemy models (DB).

## Files
- `schemas.py` — Pydantic: ForecastPoint, ChatRequest/Response, AlertRecord, LocationMatch
- `db_models.py` — SQLAlchemy ORM: forecast_cycles, alerts, user_locations, gazetteer, observations

## Key Tables
| Table | Engine | Purpose |
|-------|--------|---------|
| forecast_cycles | Postgres | Registered GFS/ECMWF runs (model, run_time, valid_range, zarr_path) |
| alerts | PostGIS | CAP alerts with geometry column |
| user_locations | PostGIS | User subscriptions with point (for ST_Intersects) |
| gazetteer | Postgres + pg_trgm | ~600k Indian place names |
| observations | TimescaleDB | Station timeseries (hypertable) |

## Rules
- No MongoDB — Postgres JSONB covers document cases
- Alembic manages all migrations (alembic/ directory)
