"""
Redis Cache Client — Point forecast cache + semantic query cache.

Every point query hits Redis first (TTL 1h). Precomputed forecasts
for top 5000 Indian towns are warmed after each GFS cycle.
"""
