# Session 01 — Step 02: Project Structure, Scaffold Files, Initial Commit

**Date:** 2026-08-31  
**Time:** ~21:50 – 22:00 IST  
**Goal:** Create the full project directory structure with verbose folder names, scaffold every file with descriptive docstrings, and make the initial git commit.

---

## Directory Structure (verbose, for development)

```
app/
├── api_gateway/                  # FastAPI route handlers
│   ├── __init__.py
│   ├── deps.py                   # Dependency injection (DB session, Redis, settings)
│   └── routes/
│       ├── __init__.py
│       ├── chat.py               # Primary conversational endpoint
│       ├── weather.py            # Direct REST weather queries
│       ├── alerts.py             # Alert endpoints + push subscription
│       └── websocket.py          # Real-time WebSocket push
├── llm_orchestrator/             # Intent classification, tool dispatch, response phrasing
│   ├── __init__.py
│   ├── router.py                 # Main orchestrator: intent → tools → phrased response
│   ├── intent.py                 # Small/fast model intent classifier (~100ms)
│   └── templates.py              # Multilingual response templates (verified, no hallucination)
├── weather_tools/                # The 5 spec tools + location resolver
│   ├── __init__.py
│   ├── base.py                   # Common tool interface
│   ├── current.py                # get_current(lat, lon)
│   ├── forecast.py               # get_forecast(lat, lon, hours)
│   ├── alerts_tool.py            # get_alerts(geom)
│   ├── climatology.py            # get_climatology(lat, lon, var, years)
│   ├── advisory.py               # get_advisory(crop, stage, forecast)
│   └── location_resolver.py      # Gazetteer fuzzy match (pg_trgm, ~600k rows)
├── data_sources/                 # All normalize to ForecastPoint
│   ├── __init__.py
│   ├── base.py                   # ForecastPoint schema + base source interface
│   ├── openmeteo.py              # Open-Meteo (free, always-on fallback)
│   ├── imd.py                    # IMD Mausam (undocumented, verify before demo)
│   ├── gfs.py                    # GFS via Zarr store (ingested by pipeline)
│   ├── ecmwf.py                  # ECMWF Open Data (IFS 0.25°)
│   └── era5.py                   # ERA5 reanalysis (1940→present)
├── schemas_and_models/           # Pydantic + SQLAlchemy
│   ├── __init__.py
│   ├── schemas.py                # Request/response Pydantic models
│   └── db_models.py              # ORM models (PostGIS + TimescaleDB tables)
├── database/                     # Connection management
│   ├── __init__.py
│   ├── session.py                # Async SQLAlchemy engine + session factory
│   └── redis_cache.py            # Redis client (TTL 1h, forecast precompute)
├── ingestion_pipelines/          # Runs on own clock, never in request path
│   ├── __init__.py
│   ├── gfs_pipeline.py           # GFS cycle: herbie → cfgrib → xarray → Zarr → Postgres
│   ├── sachet_poller.py          # SACHET CAP-XML → PostGIS → FCM push (every 60s)
│   ├── wis2_subscriber.py        # WIS2 MQTT subscriber (globalbroker.meteo.fr)
│   └── scheduler.py              # APScheduler trigger config
├── external_services/            # Third-party service clients
│   ├── __init__.py
│   ├── bhashini.py               # Bhashini ULCA ASR/MT/TTS (22 languages)
│   └── fcm.py                    # Firebase Cloud Messaging (alert push)
├── config.py                     # pydantic-settings, UPPER_CASE fields
└── main.py                       # FastAPI app entry point

alembic/
└── versions/                     # DB migration scripts

docker/                           # Dockerfile + docker-compose.yml (future)

tests/
└── __init__.py

logs/
└── 01-session/
    ├── step-01.md
    └── step-02.md (this file)
```

**Note:** Verbose folder names (e.g. `api_gateway`, `llm_orchestrator`, `weather_tools`) are for development clarity. Will be renamed to shorter names (`api`, `core`, `tools`, etc.) before shipping.

---

## Final structure (what will ship)

```
app/          →  api/           (routes)
              →  core/          (LLM orchestrator)
              →  tools/         (weather tools)
              →  sources/       (data sources)
              →  models/        (schemas + DB models)
              →  db/            (session + cache)
              →  ingestion/     (pipelines)
              →  services/      (external services)
```

---

## Commands Run

### 1. Create all directories

```bash
mkdir -p app/api_gateway/routes app/llm_orchestrator app/weather_tools app/data_sources app/schemas_and_models app/database app/ingestion_pipelines app/external_services alembic/versions docker tests
```

### 2. Create `__init__.py` files

```bash
for dir in app app/api_gateway app/api_gateway/routes app/llm_orchestrator app/weather_tools app/data_sources app/schemas_and_models app/database app/ingestion_pipelines app/external_services tests; do
  touch "$dir/__init__.py"
done
```

### 3. Create scaffold files (each with descriptive docstring)

Created via `cat > <file> << 'EOF'` for each:

| File | Purpose |
|------|---------|
| `app/main.py` | FastAPI app entry, `/health` endpoint |
| `app/config.py` | pydantic-settings, all env vars, UPPER_CASE fields |
| `app/api_gateway/routes/chat.py` | Chat conversational endpoint |
| `app/api_gateway/routes/weather.py` | Direct REST weather queries |
| `app/api_gateway/routes/alerts.py` | Alert endpoints |
| `app/api_gateway/routes/websocket.py` | WebSocket real-time push |
| `app/api_gateway/deps.py` | FastAPI dependency injection |
| `app/llm_orchestrator/router.py` | Intent → tools → response orchestrator |
| `app/llm_orchestrator/intent.py` | Fast intent classifier |
| `app/llm_orchestrator/templates.py` | Multilingual verified templates |
| `app/weather_tools/base.py` | Base tool interface |
| `app/weather_tools/current.py` | get_current tool |
| `app/weather_tools/forecast.py` | get_forecast tool |
| `app/weather_tools/alerts_tool.py` | get_alerts tool |
| `app/weather_tools/climatology.py` | get_climatology tool |
| `app/weather_tools/advisory.py` | get_advisory tool |
| `app/weather_tools/location_resolver.py` | Gazetteer fuzzy matcher |
| `app/data_sources/base.py` | ForecastPoint schema + base interface |
| `app/data_sources/openmeteo.py` | Open-Meteo client |
| `app/data_sources/imd.py` | IMD Mausam client |
| `app/data_sources/gfs.py` | GFS Zarr reader |
| `app/data_sources/ecmwf.py` | ECMWF open data client |
| `app/data_sources/era5.py` | ERA5 historical client |
| `app/schemas_and_models/schemas.py` | Pydantic models |
| `app/schemas_and_models/db_models.py` | SQLAlchemy ORM models |
| `app/database/session.py` | Async DB session factory |
| `app/database/redis_cache.py` | Redis cache client |
| `app/ingestion_pipelines/gfs_pipeline.py` | GFS ingest pipeline |
| `app/ingestion_pipelines/sachet_poller.py` | SACHET CAP poller |
| `app/ingestion_pipelines/wis2_subscriber.py` | WIS2 MQTT subscriber |
| `app/ingestion_pipelines/scheduler.py` | APScheduler setup |
| `app/external_services/bhashini.py` | Bhashini ASR/MT/TTS |
| `app/external_services/fcm.py` | Firebase push notifications |
| `.env.example` | Template for all env vars |
| `.gitignore` | Updated with .env, IDE, OS ignores |

### 4. Config change: UPPER_CASE field names

All `Settings` fields renamed from `snake_case` to `UPPER_CASE` (e.g. `database_url` → `DATABASE_URL`). `case_sensitive=False` so env var matching still works.

### 5. Initial git commit

```bash
git add -A && git status
git commit -m "chore: initial project scaffold — deps, directory structure, config ..."
```

**Result:** `264ee84` — 53 files, 3761 insertions.

---

**End of Session 01. Next session starts a new log series (02-session/).**
