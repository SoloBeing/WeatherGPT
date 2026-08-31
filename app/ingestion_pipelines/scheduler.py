"""
Scheduler Setup — APScheduler configuration for all ingestion jobs.

GFS cycles are cron-shaped. This module sets up the triggers:
  - GFS ingest: 4x daily, offset by ~3.5h from cycle time
  - SACHET poll: every 60s
  - Forecast precompute: after each GFS ingest (top 5000 towns)
"""
