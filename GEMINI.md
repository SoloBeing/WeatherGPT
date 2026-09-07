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
├── core/                     → router, anti-hallucination templates, resilience (SingleFlight, backoff)
├── tools/                    → current, forecast, alerts, marine, aviation, advisory, climatology, location_resolver
├── data_sources/             → Open-Meteo, GFS, INCOIS, Aviation, ERA5
├── models/                   → Pydantic schemas (NWP, Marine, Aviation, Agromet, Climate) + SQLAlchemy ORM models
├── database/                 → async session + Redis connection pool, MinIO Zarr storage
├── pipelines/                → GFS GRIB2 pipeline, SACHET poller, scheduler
├── services/                 → Bhashini, FCM
├── config.py                 → pydantic-settings, UPPER_CASE fields
└── main.py                   → FastAPI entry point & lifespan manager
```

## Data Sources

| Source | Access | Use |
|--------|--------|-----|
| Open-Meteo | No key, REST | Primary point forecast & global fallback |
| NOAA GFS | S3 anon (Herbie) | Raw 0.25° GRIB2 NWP cropped to India bounding box |
| INCOIS / Open-Meteo Marine | REST | Wave height, swell, currents, sea state & PFZ advisory |
| NOAA Aviation Weather Center | REST (METAR) | Live aerodrome METAR observations & flight categories |
| ICAR / IMD Agromet | Deterministic Engine | Phenology-driven crop advisories & pest alerts |
| ECMWF ERA5 | CDS / Open-Meteo Archive | 1940→present reanalysis & WMO 30-year climate normals |
| NDMA SACHET | Live JSON / CAP-XML | National disaster alerts & official warning feed |

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

**Last session:** Dev Session 07 — Multi-Domain Expansion, Provenance Transparency & Review Resolution (2026-09-07)  
**What exists:**
- ✅ **POST /chat** works end-to-end with dynamic source attribution and multi-domain tools (GFS NWP, Open-Meteo, INCOIS Marine, Aviation METAR, ICAR Agromet, ECMWF ERA5, and SACHET alerts), anti-hallucination verified template injection, and raw structured payloads in `ChatResponse.data` for rich UI widgets
- ✅ **Full SIH Meteorological Tool Suite:**
  - `get_current_weather` & `get_forecast` — GFS 0.25° NWP Zarr store with Open-Meteo fallback
  - `get_alerts` — NDMA SACHET active emergency alerts with polygon/circle/district spatial matching
  - `get_marine_weather` — Open-Meteo Marine + INCOIS sea state, wave/swell analytics, and PFZ fishing advisories
  - `get_aviation_weather` — NOAA Aviation Weather Center live METAR, flight category (VFR/MVFR/IFR), ceiling, and visibility
  - `get_agricultural_advisory` — ICAR / IMD Agromet rule engine evaluating 5-day NWP forecasts against crop growth stages
  - `get_climatology` — ECMWF ERA5 multi-decadal reanalysis normals, standard deviation, and decadal warming trends
- ✅ **Direct REST Weather & Alert Endpoints:**
  - `GET /weather/current?location=...` (or `?lat=...&lon=...`) — raw JSON `ForecastPoint`
  - `GET /weather/forecast?location=...&days=5` — structured `ForecastTimeline`
  - `GET /weather/locations?q=...` — autocomplete & geocoding `LocationMatch[]`
  - `GET /alerts?location=...` — active disaster alerts for target region
  - `GET /alerts/active` — all active nationwide NDMA SACHET / IMD warnings
- ✅ **POST /voice/chat** — full voice-to-voice pipeline: Audio → ASR (Bhashini/Groq Whisper) → NMT → LLM → NMT → TTS (Bhashini/gTTS) → Audio
- ✅ **GET /voice/languages** — returns 23 supported Indic language codes
- ✅ **Transparent Provenance:** `data_quality: "verified" | "synthetic"` across all models, preventing silent synthetic data substitution
- ✅ **Proactive Alert Push:** Live SACHET poller wired to both WebSocket (`/ws/alerts` with initial `type: "init"` snapshot and live `type: "weather_alert"` broadcasts) and FCM topic push (`weather_alerts_extreme`, `weather_alerts_severe`)
- ✅ `ForecastPoint`, `DailyForecast`, `HourlyForecast`, `ForecastTimeline`, `MarinePoint`, `AviationWeather`, `CropAdvisoryReport`, `ClimatologyReport`, `MonthlyClimateNormal`, `AlertRecord`, `AlertListResponse`, `ChatRequest/Response`, `LocationMatch`, `VoiceChatResponse` schemas in `app/models/schemas.py`
- ✅ **Anti-Hallucination Verified Templates:** Multi-language templates (`app/core/templates.py`) ensuring exact factual preservation in Indic languages and automatic template fallback during vendor LLM outages
- ✅ **SQLAlchemy ORM Models** (`ForecastCycle`, `Alert`, `UserLocation`, `Gazetteer`, `Observation`) with GeoAlchemy2 PostGIS types and TimescaleDB hypertable target in `app/models/db_models.py`
- ✅ **Alembic async migrations** configured with `0001_initial_schema.py` and `0002_performance_and_spatial_indexes.py` (GIN trigram, composite indexes)
- ✅ **MinIO / local Zarr storage layer** (`app/database/minio_client.py`) with automatic partitioning and chunking
- ✅ **GFS GRIB2 Ingestion Pipeline** (`app/pipelines/gfs_pipeline.py`) fetching NOAA GFS 0.25° models via `Herbie`, subsetting to India bounding box (6°-38°N, 68°-98°E), decoding via `cfgrib`/`xarray`, and persisting to Zarr
- ✅ **APScheduler background jobs** (`app/pipelines/scheduler.py`) running 4x daily GFS ingest, 60s SACHET alert polling, and Redis cache warming for 18 key Indian state capitals
- ✅ **Resilience & High Performance:** `SingleFlight` request coalescing, asyncpg pool (`DB_POOL_SIZE=20`), Redis `ConnectionPool`, HTTP client connection pooling (`httpx.Limits`), and vectorized 1D coordinate slicing
- ✅ **Containerization & Kubernetes:** Multi-stage Dockerfile with Astral `uv`, non-root security (`weathergpt:10001`), `docker-compose.yml` (PostGIS, Redis, MinIO, API, Worker), 13 Kubernetes manifests with HPA, and end-to-end automated demo runner (`scripts/demo.py`)
- ✅ **Frontend Developer Tooling & Types:**
  - TypeScript interface definitions in `docs/weathergpt-types.ts`
  - OpenAPI 3.1 specification in `docs/openapi.json`
  - Integration and handoff guide in `docs/FRONTEND_HANDOFF.md`
- ✅ **Dev Session 01 (`tests/test_session_06.py`)** — Standardized on pytest + pytest-asyncio, decoupled weather tools test via `synthetic_gfs_cycle` fixture, eliminated dead imports and magic coordinates.
- ✅ **Dev Session 02 (`alembic/`)** — Migration infrastructure audit: protected side-effect registrations (`geoalchemy2` & `db_models`) with `# noqa: F401`.
- ✅ **Dev Session 03 (`app/` core & lifespan)** — Modernized FastAPI lifecycle with async `lifespan` context manager, clean shutdown handlers for HTTP clients and pools, guarded file handles with `try...finally`.
- ✅ **Dev Session 04 (`app/` production layout)** — Shortened development scaffolding module names to production hierarchy (`app/api/`, `app/core/`, `app/tools/`, `app/models/`, `app/pipelines/`, `app/services/`).
- ✅ **Dev Session 05 (Robustness & Fault Tolerance)** — Jittered exponential backoff, HTTP error classification, Zarr integrity validation, and GFS cycle failover.
- ✅ **Dev Session 06 (Scalability & Performance Auditing)** — Asyncpg (`DB_POOL_SIZE=20`), Redis (`ConnectionPool`), and HTTP client (`httpx.Limits`) connection pooling, `SingleFlight` coalescing, vectorized 1D Zarr index slicing, and GIN trigram indexes.
- ✅ **Dev Session 07 (Multi-Domain SIH Expansion, Provenance & Peer Review Resolution)** — Resolved all 12 peer review findings:
  - **Marine & Coastal Domain:** Open-Meteo Marine + INCOIS Douglas sea state classification, wave/swell analytics, and Potential Fishing Zone (PFZ) advisory engine (`get_marine_weather`).
  - **Aviation Weather Domain:** NOAA Aviation Weather Center live METAR integration with flight category (VFR/MVFR/IFR/LIFR), cloud ceilings, runway visibility, and 25+ Indian airport mappings (`get_aviation_weather`).
  - **Agricultural Agromet Domain:** ICAR / IMD Agromet rule engine evaluating 5-day NWP rain/temperature/wind forecasts against crop growth stages for Rice, Wheat, Cotton, Mustard, Pulses, Sugarcane (`get_agricultural_advisory`).
  - **Historical Climatology Domain:** ECMWF ERA5 reanalysis archive client computing WMO 30-year normals, standard deviations, decadal warming trends, and recent anomalies (`get_climatology`).
  - **Data Provenance Transparency:** Surfaced `data_quality: "verified" | "synthetic"` across all schemas and explicitly labelled synthetic sandbox fallbacks without silent masquerading.
  - **Live NDMA SACHET JSON Feed:** Integrated live `FetchAllAlertDetails` endpoint with strict `expires_at >= now` filtering and honest `"status": "Exercise"` sandbox tagging.
  - **Proactive FCM Push Notification Wiring:** Connected SACHET poller listener events directly to `fcm_service.push_alert` and `app/main.py` startup lifespan.
  - **Anti-Hallucination Verified Response Templates:** Integrated `app/core/templates.py` formatters across all 6 meteorological tools, enforcing exact factual preservation in Indic languages and providing verified template fallback during vendor LLM outages.
  - **Dynamic Source Attribution:** Replaced hardcoded sources in `/chat` with dynamic inspection of `parsed_res["source"]` for NOAA GFS, INCOIS, Aviation Weather Center, ICAR Agromet, ECMWF ERA5, and SACHET NDMA.
  - **API Hygiene & Configuration:** Fixed CORS credentials with wildcard origins (`allow_credentials=False`), sanitized 500 error responses in `/chat`, reported `"degraded"` status in `/health` when databases are offline, and auto-detected Groq keys (`gsk_...`).
  - **Frontend & TypeScript Synchronization:** Synchronized `docs/FRONTEND_HANDOFF.md` and `docs/weathergpt-types.ts` with WebSocket initial snapshot (`type: "init"`), SIH domain schemas, direct REST endpoints, and `data_quality` fields.
- ✅ **Session 07 (Containerization, Kubernetes & Final Shipping)** — Multi-stage Dockerfile with Astral `uv` and non-root security (`weathergpt:10001`), full-stack `docker-compose.yml` (PostgreSQL PostGIS/TimescaleDB, Redis, MinIO, bucket init, migrations, API, and worker), 13 declarative Kubernetes manifests with Horizontal Pod Autoscaler (2-10 replicas) and NGINX Ingress WebSocket proxy, automated 8-step system demonstration runner (`scripts/demo.py`), and test suite achieving 50/50 tests passing with 0 warnings.
- **LLM Provider:** Groq (`groq/llama-3.3-70b-versatile` or `groq/openai/gpt-oss-120b` main, `groq/qwen/qwen3.8-27b` intent)
- **Data Sources Reference:** `weather_gpt_structure.md` documents 8 sources (Open-Meteo, IMD api.imd.gov.in, GFS, ECMWF, NASA POWER, WIS2.0, ERA5, MOSDAC)

## Session 07 Summary (`logs/07-session/summary.md` & `dev-logs/07-dev-session/summary.md`)

- **Focus:** Multi-stage containerization with Astral uv, Docker Compose full-stack orchestration, production Kubernetes manifests with HPA and StatefulSets, end-to-end demo runner, multi-domain SIH expansion, transparent data provenance, and peer review resolution.
- **Result:** 50/50 tests passing in ~21s with 0 warnings under strict `-W error` enforcement.

## Production Status & Roadmap Completion

All 7 core milestones and 7 dev-refactoring sessions are complete. The WeatherGPT platform is an honest, fully multi-domain, resilient meteorological system ready for live deployment and hackathon judging.

## 7-Day Roadmap (2026-08-31 → 2026-09-06) — COMPLETE 🎯

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
| — | **Dev-06** | ✅ Scalability & Performance Auditing (Pools, Batching, Caching) | Maintainability |
| 7 (Sep 06) | **07** | ✅ Docker Compose, K8s manifests, demo prep, final shipping | Ship |
| — | **Dev-07** | ✅ Multi-Domain SIH Expansion, Provenance Transparency & Review Resolution | Audit |




