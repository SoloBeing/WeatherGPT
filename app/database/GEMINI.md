# database — Context

## Role
Connection management for Postgres and Redis.

## Files
- `session.py` — Async SQLAlchemy engine + session factory (single Postgres: PostGIS + TimescaleDB)
- `redis_cache.py` — Redis client for point forecast cache (TTL 1h) + semantic query cache

## Rules
- All DB access is async (asyncpg driver)
- Redis is checked BEFORE any Zarr/Postgres/external read
- Precomputed forecasts for top 5000 towns are warmed in Redis after each GFS cycle
