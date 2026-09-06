# pipelines — Context

## Role
Background data ingestion. Runs on its own clock, NEVER in the request path.

## Pipelines
| Pipeline | Trigger | Flow |
|----------|---------|------|
| GFS | ~3.5h after 00/06/12/18Z cycle | herbie → cfgrib → xarray → Zarr (MinIO) → register in Postgres |
| SACHET CAP | Every 60s | CAP-XML → PostGIS geometry → ST_Intersects users → FCM + WebSocket |
| WIS2 MQTT | Long-running subscriber | MQTTS globalbroker.meteo.fr:8883 → filter India → fetch → Postgres |

## Rules
- Never block the request path
- Precompute forecasts for top 5000 Indian towns after each GFS cycle
- APScheduler manages all triggers (scheduler.py)
