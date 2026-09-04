# Session 06 — Step 05: APScheduler Setup & Lifespan Integration

**What was done:**
- Implemented `IngestionScheduler` in `app/ingestion_pipelines/scheduler.py`:
  - Configured `AsyncIOScheduler` with two automated background jobs:
    1. `job_gfs_ingestion`: Cron trigger running 4x daily (03:30, 09:30, 15:30, 21:30 UTC) matching GFS cycle availability windows.
    2. `job_sachet_poll`: Interval trigger running every 60s to poll NDMA SACHET CAP XML feed.
  - Implemented `precompute_top_towns()` to slice point forecasts from the latest Zarr store for 18 key Indian state capitals and metropolitan centers (Delhi, Mumbai, Bengaluru, Chennai, Kolkata, Hyderabad, Ahmedabad, Pune, Jaipur, Lucknow, Patna, Bhopal, Chandigarh, Bhubaneswar, Guwahati, Thiruvananthapuram, Shimla, Srinagar) and pre-warm Redis.
  - Provided `start()`, `shutdown()`, and `trigger_gfs_now()` programmatic lifecycle hooks.
- Integrated scheduler and resource cleanup into `app/main.py`:
  - Startup: starts APScheduler.
  - Shutdown: graceful teardown of scheduler, database connection pool, Redis client, and SACHET poller.
  - Health check (`GET /health`): updated to report subsystem connection status (`database`, `redis`, `scheduler_running`).
- Verified scheduler job registration, town precomputation, and FastAPI `/health` endpoint.

**Commands:**
```bash
# Verify scheduler and health endpoint
uv run python -c "
from app.ingestion_pipelines.scheduler import ingestion_scheduler, precompute_top_towns
from fastapi.testclient import TestClient
from app.main import app
ingestion_scheduler.setup_jobs()
assert len(ingestion_scheduler.scheduler.get_jobs()) == 2
client = TestClient(app)
assert client.get('/health').status_code == 200
print('Scheduler OK!')
"
```

**Notable output:**
- Registered jobs: `gfs_nwp_ingest`, `sachet_alert_poll`.
- Precomputed 18 key Indian metropolitan centers from Zarr store.
- Health endpoint returns JSON status with subsystem health.
