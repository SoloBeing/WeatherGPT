"""
get_forecast(lat, lon, hours) — Hourly/daily forecast.

Returns: up to 384h forecast (GFS), 16-day (Open-Meteo blended).
Checks Redis cache first (TTL 1h), then Zarr/Postgres, then external API.
"""
