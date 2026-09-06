# WeatherGPT — Project Memory

## What This Is

WeatherGPT is a conversational AI system for weather forecasting, alerts, and climate information targeting India. It is being built for a competition with a 7-day deadline starting 2026-08-31.

## Core Design Principle

**The LLM never computes or recalls weather.** It only:
1. Parses the query into a structured intent
2. Calls tools
3. Phrases the tool output in the user's language

Every number comes from a deterministic service. This boundary is sacred.

## Tech Stack

- **Language:** Python 3.13
- **Package manager:** uv
- **API:** FastAPI + Uvicorn
- **LLM:** litellm (multi-provider tool-calling)
- **Database:** PostgreSQL with PostGIS + TimescaleDB (single instance)
- **Cache:** Redis (TTL 1h point forecasts, semantic query cache)
- **Object Store:** MinIO / S3 (Zarr stores, COGs, satellite tiles)
- **Grid Data:** xarray + zarr + cfgrib
- **GRIB Fetch:** herbie + ecmwf-opendata
- **Scheduling:** APScheduler
- **Realtime:** MQTT (paho) in, WebSocket out
- **Push:** Firebase Cloud Messaging
- **Voice + Translation:** Bhashini (ULCA) APIs
- **Deploy:** Docker Compose → K8s

## Project Structure (Development Names)

```
app/
├── api_gateway/              → routes, deps
├── llm_orchestrator/         → intent classifier, tool dispatch, templates
├── weather_tools/            → get_current, get_forecast, get_alerts, get_climatology, get_advisory, location_resolver
├── data_sources/             → Open-Meteo, IMD, GFS, ECMWF, ERA5 (all → ForecastPoint)
├── schemas_and_models/       → Pydantic schemas + SQLAlchemy ORM
├── database/                 → async session + Redis client
├── ingestion_pipelines/      → GFS pipeline, SACHET poller, WIS2 subscriber, scheduler
├── external_services/        → Bhashini, FCM
├── config.py                 → pydantic-settings, UPPER_CASE fields
└── main.py                   → FastAPI entry point
```

These verbose names will be shortened before shipping (api_gateway→api, llm_orchestrator→core, etc.).

## Data Sources

| Source | Access | Use |
|--------|--------|-----|
| Open-Meteo | No key, REST | Primary fallback, blended forecasts |
| IMD Mausam | JSON (undocumented) | Official Indian data, verify before demo |
| NOAA GFS | S3 anon | Raw 0.25° GRIB2, 384h |
| ECMWF Open Data | ecmwf-opendata pkg | IFS 0.25°, better skill |
| ERA5 | cdsapi | 1940→present reanalysis |
| SACHET | CAP-XML feed | India CAP alerts |
| WIS2.0 | MQTTS | Live push notifications |

## Build Priority (from spec)

1. FastAPI + Open-Meteo + one tool + text chat ← **carries the demo**
2. SACHET alerts + push ← **carries the demo**
3. Bhashini voice ← **carries the demo**
4. GFS/Zarr pipeline ← carries "real-time meteorological systems" score
5. WRF ← carries "real-time meteorological systems" score

## Session Log Convention

- Regular build sessions:
  - Logs live in `logs/XX-session/step-YY.md`
  - Each step records: what was done, exact bash commands, notable output
  - **Write the step log AND git commit (code + step log together) BEFORE moving to the next step.** Never batch logs retroactively.
  - Session summary lives in `logs/XX-session/summary.md` (committed alongside final session state)

- Dev-Sessions (Cleaning, Refactoring, Auditing, Maintainability):
  - Have a separate, more verbose log under `dev-logs/` (e.g. `dev-logs/XX-dev-session/summary.md`).
  - No granular `step-YY.md` files during the auditing/fixing process.
  - **Workflow:**
    1. Flag everything first (walk through & catalog all items).
    2. Systematically fix each flagged item one by one.
    3. **Commit after EVERY individual fix** (e.g., 10 items flagged = 10 distinct, atomic commits for each respective item).
    4. Write a comprehensive summary dev-log in `dev-logs/` after all fixes are completed at the end of the session.


## Configuration

- All settings in `app/config.py` via pydantic-settings
- Field names are UPPER_CASE (e.g. `settings.DATABASE_URL`)
- Env vars loaded from `.env` file (template in `.env.example`)
- `case_sensitive=False` so env matching is flexible

## Key Constraints

- No MongoDB — Postgres JSONB covers document cases
- Don't run WRF live — pre-compute and store as Zarr
- Multilingual: use verified templates for factual core, LLM only for conversational glue
- IMD endpoints are undocumented/unversioned — always have Open-Meteo fallback
- Every data source normalises to `ForecastPoint` with `source` and `issued_at` fields

## Current State (updated each session)

**Last session:** Dev Session 02 (2026-09-05)  
**What exists:**
- ✅ **POST /chat** works end-to-end with Open-Meteo forecasts and SACHET/IMD active disaster alerts
- ✅ **POST /voice/chat** — full voice-to-voice pipeline: Audio → ASR → NMT → LLM → NMT → TTS → Audio
- ✅ **GET /voice/languages** — returns 23 supported language codes
- ✅ `ForecastPoint`, `DailyForecast`, `HourlyForecast`, `ForecastTimeline`, `AlertRecord`, `AlertListResponse`, `ChatRequest/Response`, `LocationMatch`, `VoiceChatResponse` schemas
- ✅ **SQLAlchemy ORM Models** (`ForecastCycle`, `Alert`, `UserLocation`, `Gazetteer`, `Observation`) with GeoAlchemy2 PostGIS types and TimescaleDB hypertable target in `app/schemas_and_models/db_models.py` and `app/schemas_and_models/orm.py`
- ✅ **Alembic async migrations** configured in `alembic.ini` and `alembic/env.py` with initial migration `0001_initial_schema.py` supporting `postgis`, `pg_trgm`, and `timescaledb`
- ✅ **MinIO / local Zarr storage layer** (`app/database/minio_client.py`) with automatic partitioning and chunking for millisecond spatial slicing
- ✅ **GFS GRIB2 Ingestion Pipeline** (`app/ingestion_pipelines/gfs_pipeline.py`) fetching NOAA GFS 0.25° models via `Herbie`, subsetting to India bounding box (6°-38°N, 68°-98°E), decoding via `cfgrib`/`xarray`, deriving 12 meteorological variables, and persisting to Zarr
- ✅ **APScheduler background jobs** (`app/ingestion_pipelines/scheduler.py`) running 4x daily GFS ingest (03:30, 09:30, 15:30, 21:30 UTC), 60s SACHET alert feed polling, and precomputing forecasts for 18 key Indian state capitals and metropolitan hubs into Redis
- ✅ **GFS data source reader** (`app/data_sources/gfs.py`) and weather tool integration with automatic GFS Zarr primary and Open-Meteo fallback
- ✅ Open-Meteo client (`fetch_current` + `fetch_forecast` with 15 daily & 8 hourly params)
- ✅ SACHET CAP-XML Poller & active alert registry with spatial polygon and district/state matching
- ✅ Location resolver (Open-Meteo geocoding + 36 Indian States/UTs Gazetteer)
- ✅ `get_current_weather`, `get_forecast`, `get_alerts` tools with Redis cache-aside
- ✅ Redis cache client (`database/redis_cache.py`) with fail-open fallback
- ✅ WebSocket live alert streaming (`api_gateway/routes/websocket.py` on `/ws/alerts`)
- ✅ FCM push notification service (`external_services/fcm.py`) with severity topic dispatch
- ✅ Bhashini ULCA client (`external_services/bhashini.py`) — ASR, NMT, TTS with pipeline config caching
- ✅ Groq Whisper ASR fallback + gTTS TTS fallback (graceful degradation)
- ✅ LLM orchestrator (litellm tool-calling loop, multi-turn conversation session history)
- ✅ Response templates — 6 languages: English, Hindi, Tamil, Telugu, Bengali, Marathi (verified native-script)
- ✅ FastAPI app with CORS, /chat, /voice/chat, /voice/languages, /ws/alerts, /health with subsystem reporting
- ✅ **Dev Session 01 (`tests/test_session_06.py`)** — Standardized on pytest + pytest-asyncio, decoupled weather tools test via `synthetic_gfs_cycle` fixture, eliminated dead imports and magic coordinates, resolved brittle geocoding and hardcoded dates.
- ✅ **Dev Session 02 (`alembic/`)** — Migration infrastructure audit: protected side-effect registrations (`geoalchemy2` & `db_models`) with `# noqa: F401` against linter auto-stripping, condensed boilerplate template docstrings in `alembic/env.py`, and verified `script.py.mako` templating.
- ✅ **Dev Session 03 (`app/` core & lifespan)** — Modernized FastAPI lifecycle with async `lifespan` context manager, wired clean shutdown handlers for HTTP clients (`BhashiniService`, `openmeteo_client`) and background pools, guarded audio uploads and Zarr dataset file handles with `try...finally`, enabled Zarr format 3 compliance (`consolidated=False`), and configured strict warning-free pytest filters.
- **LLM Provider:** Groq (`groq/openai/gpt-oss-120b` main, `groq/qwen/qwen3.8-27b` intent)
- **Data Sources Reference:** `weather_gpt_structure.md` documents 8 sources (Open-Meteo, IMD api.imd.gov.in, GFS, ECMWF, NASA POWER, WIS2.0, ERA5, MOSDAC)

## Status: Holding Session 07 — Focusing on Dev Sessions (Refactoring, Maintainability & Scalability)

Session 07 (Docker Compose, K8s manifests, final shipping) is held until further notice to prioritize polishing, refactoring, and strengthening the existing codebase.

### Upcoming Dev Sessions Focus:

1. **Dev Session 04: Architecture & Module Naming Polish**
   - Execute planned verbose name shortening from development scaffold:
     - `api_gateway/` → `api/`
     - `llm_orchestrator/` → `core/`
     - `weather_tools/` → `tools/`
     - `schemas_and_models/` → `models/`
     - `ingestion_pipelines/` → `pipelines/`
     - `external_services/` → `services/`
   - Update all import paths cleanly across `app/`, `tests/`, and `alembic/`.

2. **Dev Session 05: Robustness & Data Source Fault Tolerance**
   - Enhance resilience for GFS and Open-Meteo clients (exponential backoff, circuit breaking, typed exceptions).
   - Ensure Zarr store index listing filters strictly for valid model cycles (`gfs_*`) to prevent uninitialized directory collisions.
   - Add comprehensive mock fixtures in tests for offline test reproducibility across all test suites (Sessions 02–05).

3. **Dev Session 06: Scalability & Performance Auditing**
   - Optimize spatial point-slicing in `GFSClient` with persistent dataset handles or caching open stores.
   - Validate TimescaleDB hypertable query plans and PostGIS spatial indexing (`gist(geom)`).
   - Expand Redis precomputation strategies for top meteorological queries and alert lookups.

## 7-Day Roadmap (2026-08-31 → 2026-09-06)

| Day | Session | Focus | Spec Priority |
|-----|---------|-------|---------------|
| 1 (Aug 31) | 01 | ✅ Deps, scaffold, memory | Setup |
| 2 (Sep 01) | 02 | ✅ FastAPI + Open-Meteo + get_current + chat | P1: carries demo |
| 3 (Sep 02) | 03 | ✅ get_forecast + Redis cache + multi-turn chat | P1: carries demo |
| 4 (Sep 03) | 04 | ✅ SACHET alerts + FCM push + WebSocket | P2: carries demo |
| 5 (Sep 04) | 05 | ✅ Bhashini voice (ASR + TTS) + multilingual templates | P3: carries demo |
| 6 (Sep 05) | 06 | ✅ GFS/Zarr ingestion pipeline + DB models + Alembic | P4: meteorological score |
| — | **Dev-01** | ✅ Test Suite Polish (`test_session_06.py`), pytest runner, decoupling | Refactor |
| — | **Dev-02** | ✅ Alembic Migration Audit (`env.py`, F401 protection, docstrings) | Maintainability |
| — | **Dev-03** | ✅ App Core & Lifespan Audit (`app/`, `try...finally`, warning hygiene) | Maintainability |
| — | **Dev-04+** | Codebase Polish: Architecture & Module Naming Polish, Fault Tolerance | Maintainability |
| 7 (Sep 06) | 07 | *[On Hold]* Docker Compose, polish, demo prep, final tests | Ship |


