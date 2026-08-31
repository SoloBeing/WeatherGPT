"""
Database Session — Async SQLAlchemy engine + session factory.

Single Postgres instance runs both PostGIS (alert polygons, gazetteer)
and TimescaleDB (station timeseries). Connection pool managed here.
"""
