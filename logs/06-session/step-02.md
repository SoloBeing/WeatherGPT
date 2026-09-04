# Session 06 — Step 02: Alembic Migrations Setup

**What was done:**
- Configured Alembic for async migrations in `alembic.ini` and `alembic/env.py`.
- Connected `env.py` dynamically to `app.config.settings.DATABASE_URL` and `app.database.session.Base.metadata`.
- Added GeoAlchemy2 spatial comparator integration.
- Created `alembic/script.py.mako` migration template.
- Authored initial migration `alembic/versions/0001_initial_schema.py`:
  - PostgreSQL extensions: `postgis`, `pg_trgm`, `timescaledb`.
  - Tables: `forecast_cycles`, `alerts`, `user_locations`, `gazetteer`, `observations`.
  - GiST spatial indexes on PostGIS geometry columns (`alerts.geom`, `user_locations.geom`, `gazetteer.geom`).
  - TimescaleDB hypertable conversion for `observations(recorded_at)`.
- Verified complete SQL DDL generation via `alembic upgrade head --sql`.

**Commands:**
```bash
# Verify static SQL DDL generation
uv run alembic upgrade head --sql
```

**Notable output:**
- Generated clean transactional DDL with PostGIS geometry types and GiST indices.
- Hypertable DDL block generated for TimescaleDB.
