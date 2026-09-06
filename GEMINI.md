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

## Project Structure (Production Layout)

```
app/
├── api/                      → FastAPI routes (chat, voice, websocket, alerts, weather) & deps
├── core/                     → intent classifier, tool dispatch, response templates
├── tools/                    → get_current, get_forecast, get_alerts, get_climatology, get_advisory, location_resolver
├── data_sources/             → Open-Meteo, IMD, GFS, ECMWF, ERA5 (all → ForecastPoint)
├── models/                   → Pydantic schemas + SQLAlchemy ORM models
├── database/                 → async session + Redis client, MinIO Zarr storage
├── pipelines/                → GFS pipeline, SACHET poller, WIS2 subscriber, scheduler
├── services/                 → Bhashini, FCM
├── config.py                 → pydantic-settings, UPPER_CASE fields
└── main.py                   → FastAPI entry point
```

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


## Development Rules & Testing Invariant

- **Immediate Pytest Verification:** Every time you edit or write code (Python files, configurations, schemas, migrations, or tests — excluding documentation markdowns), run `uv run pytest` immediately after that edit to check if anything broke and detect regressions at the earliest possible moment before proceeding.


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

**Last session:** Dev Session 05 (2026-09-06)  
**What exists:**
- ✅ **POST /chat** works end-to-end with Open-Meteo forecasts and SACHET/IMD active disaster alerts
- ✅ **POST /voice/chat** — full voice-to-voice pipeline: Audio → ASR → NMT → LLM → NMT → TTS → Audio
- ✅ **GET /voice/languages** — returns 23 supported language codes
- ✅ `ForecastPoint`, `DailyForecast`, `HourlyForecast`, `ForecastTimeline`, `AlertRecord`, `AlertListResponse`, `ChatRequest/Response`, `LocationMatch`, `VoiceChatResponse` schemas in `app/models/schemas.py`
- ✅ **SQLAlchemy ORM Models** (`ForecastCycle`, `Alert`, `UserLocation`, `Gazetteer`, `Observation`) with GeoAlchemy2 PostGIS types and TimescaleDB hypertable target in `app/models/db_models.py` and `app/models/orm.py`
- ✅ **Alembic async migrations** configured in `alembic.ini` and `alembic/env.py` with initial migration `0001_initial_schema.py` supporting `postgis`, `pg_trgm`, and `timescaledb`
- ✅ **MinIO / local Zarr storage layer** (`app/database/minio_client.py`) with automatic partitioning and chunking for millisecond spatial slicing
- ✅ **GFS GRIB2 Ingestion Pipeline** (`app/pipelines/gfs_pipeline.py`) fetching NOAA GFS 0.25° models via `Herbie`, subsetting to India bounding box (6°-38°N, 68°-98°E), decoding via `cfgrib`/`xarray`, deriving 12 meteorological variables, and persisting to Zarr
- ✅ **APScheduler background jobs** (`app/pipelines/scheduler.py`) running 4x daily GFS ingest (03:30, 09:30, 15:30, 21:30 UTC), 60s SACHET alert feed polling, and precomputing forecasts for 18 key Indian state capitals and metropolitan hubs into Redis
- ✅ **GFS data source reader** (`app/data_sources/gfs.py`) and weather tool integration with automatic GFS Zarr primary and Open-Meteo fallback
- ✅ Open-Meteo client (`fetch_current` + `fetch_forecast` with 15 daily & 8 hourly params)
- ✅ SACHET CAP-XML Poller & active alert registry with spatial polygon and district/state matching in `app/pipelines/sachet_poller.py`
- ✅ Location resolver (Open-Meteo geocoding + 36 Indian States/UTs Gazetteer) in `app/tools/location_resolver.py`
- ✅ `get_current_weather`, `get_forecast`, `get_alerts` tools with Redis cache-aside in `app/tools/`
- ✅ Redis cache client (`app/database/redis_cache.py`) with fail-open fallback
- ✅ WebSocket live alert streaming (`app/api/routes/websocket.py` on `/ws/alerts`)
- ✅ FCM push notification service (`app/services/fcm.py`) with severity topic dispatch
- ✅ Bhashini ULCA client (`app/services/bhashini.py`) — ASR, NMT, TTS with pipeline config caching
- ✅ Groq Whisper ASR fallback + gTTS TTS fallback (graceful degradation)
- ✅ LLM orchestrator (`app/core/router.py`) with litellm tool-calling loop, multi-turn conversation session history
- ✅ Response templates — 6 languages: English, Hindi, Tamil, Telugu, Bengali, Marathi (`app/core/templates.py`)
- ✅ FastAPI app with CORS, /chat, /voice/chat, /voice/languages, /ws/alerts, /health with subsystem reporting in `app/api/`
- ✅ **Dev Session 01 (`tests/test_session_06.py`)** — Standardized on pytest + pytest-asyncio, decoupled weather tools test via `synthetic_gfs_cycle` fixture, eliminated dead imports and magic coordinates, resolved brittle geocoding and hardcoded dates.
- ✅ **Dev Session 02 (`alembic/`)** — Migration infrastructure audit: protected side-effect registrations (`geoalchemy2` & `db_models`) with `# noqa: F401` against linter auto-stripping, condensed boilerplate template docstrings in `alembic/env.py`, and verified `script.py.mako` templating.
- ✅ **Dev Session 03 (`app/` core & lifespan)** — Modernized FastAPI lifecycle with async `lifespan` context manager, wired clean shutdown handlers for HTTP clients (`BhashiniService`, `openmeteo_client`) and background pools, guarded audio uploads and Zarr dataset file handles with `try...finally`, enabled Zarr format 3 compliance (`consolidated=False`), and configured strict warning-free pytest filters (`error` default with third-party ignores).
- ✅ **Dev Session 04 (`app/` production layout)** — Shortened development scaffolding module names to production hierarchy (`app/api/`, `app/core/`, `app/tools/`, `app/models/`, `app/pipelines/`, `app/services/`), migrated all imports across application, Alembic, and tests, aligned subpackage documentation, and verified 100% test pass rate with 0 warnings.
- ✅ **Dev Session 05 (Robustness & Fault Tolerance)** — Implemented jittered exponential backoff and error classification (`app/core/resilience.py`), hardened Open-Meteo, Bhashini, and Location Resolver against transient network and rate-limit errors, added Zarr store integrity validation and GFS cycle failover (`app/database/minio_client.py`, `app/data_sources/gfs.py`), and established a 27-test offline test suite across services, storage, and data sources with 0 warnings under strict `-W error` enforcement.
- **LLM Provider:** Groq (`groq/openai/gpt-oss-120b` main, `groq/qwen/qwen3.8-27b` intent)
- **Data Sources Reference:** `weather_gpt_structure.md` documents 8 sources (Open-Meteo, IMD api.imd.gov.in, GFS, ECMWF, NASA POWER, WIS2.0, ERA5, MOSDAC)

## Dev Session 05 Summary (`dev-logs/05-dev-session/summary.md`)

- **Focus:** Resilient HTTP retry logic with jittered backoff, error classification, Zarr storage integrity checks with cycle failover, and comprehensive offline test mocking.
- **Commits:**
  - `2eb5655`: `feat(core): implement resilient HTTP retry logic with jittered backoff and error classification`
  - `9f058ef`: `refactor(data_sources): add jittered backoff retries and error classification to Open-Meteo client`
  - `dc2b964`: `refactor(services): harden Bhashini service with resilient inference retries, 401 recovery, and backoff`
  - `8b189af`: `refactor(tools): harden location resolver with geocoding retries and offline gazetteer fallback`
  - `2e9f2d6`: `feat(database): implement Zarr store integrity validation and corruption guardrails`
  - `ec071de`: `refactor(data_sources): add cycle failover and validation to GFS data source reader`
  - `d056651`: `test(resilience): add offline mock fixtures and test suite for retries, Open-Meteo, and location resolver`
  - `4767724`: `test(services): add offline test fixtures and unit tests for Bhashini and FCM`
  - `81df5bb`: `test(storage): add unit tests for Zarr store validation, corruption guardrails, and GFS failover`
- **Result:** 27/27 tests passing in ~14s with 0 warnings under strict `-W error` enforcement.

## What to Build Next: Dev Session 06 (Scalability & Performance Auditing)

Session 07 (Docker Compose, K8s manifests, final shipping) remains on hold to prioritize codebase refactoring and maintainability.

### Dev Session 06 Scope:
1. **Concurrency & Connection Pooling:**
   - Optimize HTTP and asyncpg connection pools, max connections, and idle timeouts across services.
   - Redis connection pool management and pipeline batching for spatial grid cache warming.
2. **Spatial Query Performance:**
   - Benchmark and optimize Zarr nearest-neighbor point queries and PostGIS geometry index utilization.
   - Cache-stampede prevention (dogpiling protection) for popular location forecasts.
3. **Verification & Testing Invariant:**
   - Run `uv run pytest` after every single fix and commit atomically.
   - Author comprehensive summary in `dev-logs/06-dev-session/summary.md`.

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
| — | **Dev-04** | ✅ Architecture & Module Naming Polish (`api`, `core`, `tools`, `models`) | Maintainability |
| — | **Dev-05** | ✅ Robustness & Fault Tolerance (Backoff, Retries, Offline) | Maintainability |
| — | **Dev-06** | ⏳ Scalability & Performance Auditing (Pools, Batching, Caching) | Maintainability |
| 7 (Sep 06) | 07 | *[On Hold]* Docker Compose, polish, demo prep, final tests | Ship |


