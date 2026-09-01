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

- Logs live in `logs/XX-session/step-YY.md`
- Each step records: what was done, exact bash commands, notable output
- **Git commit at every step** (commit code + step log together) rather than at session end
- Session summary lives in `logs/XX-session/summary.md` (committed alongside final session state)

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

**Last session:** 03 (2026-09-01)  
**What exists:**
- ✅ **POST /chat** works end-to-end with real Open-Meteo current weather and multi-day forecasts
- ✅ `ForecastPoint`, `DailyForecast`, `HourlyForecast`, `ForecastTimeline`, `ChatRequest/Response`, `LocationMatch` schemas
- ✅ Open-Meteo client (`fetch_current` + `fetch_forecast` with 15 daily & 8 hourly params)
- ✅ Location resolver (Open-Meteo geocoding, India-prioritised)
- ✅ `get_current_weather` & `get_forecast` tools with Redis cache-aside (TTL 1h)
- ✅ Redis cache client (`database/redis_cache.py`) with fail-open fallback
- ✅ LLM orchestrator (litellm tool-calling loop, multi-turn conversation session history)
- ✅ Response templates (English + Hindi for current and multi-day forecast)
- ✅ FastAPI app with CORS, /chat route with `session_id`, /health check
- **LLM Provider:** Groq (`groq/openai/gpt-oss-120b` main, `groq/qwen/qwen3.8-27b` intent)
- **Data Sources Reference:** `weather_gpt_structure.md` documents 8 sources (Open-Meteo, IMD api.imd.gov.in, GFS, ECMWF, NASA POWER, WIS2.0, ERA5, MOSDAC)

## Next Session (04) — What To Build

Priority 2: **SACHET alerts + FCM push + WebSocket live streaming**

### Concrete tasks:
1. **AlertRecord schema & DB model** — CAP-XML data structure in `schemas_and_models/`
2. **SACHET alert poller** — Polling & parsing NDMA SACHET CAP feeds in `ingestion_pipelines/sachet_poller.py`
3. **`get_alerts` tool** — Spatial/district alert lookup tool in `weather_tools/alerts_tool.py`
4. **WebSocket endpoint** — Real-time alert feed in `api_gateway/routes/ws.py`
5. **FCM push notifications** — Push critical alerts to devices in `external_services/fcm.py`

### Definition of done for Session 04:
You can query active disaster/weather alerts for any Indian district/state via chat, receive live alerts over WebSocket, and push alert notifications via FCM.

## 7-Day Roadmap (2026-08-31 → 2026-09-06)

| Day | Session | Focus | Spec Priority |
|-----|---------|-------|---------------|
| 1 (Aug 31) | 01 | ✅ Deps, scaffold, memory | Setup |
| 2 (Sep 01) | 02 | ✅ FastAPI + Open-Meteo + get_current + chat | P1: carries demo |
| 3 (Sep 02) | 03 | ✅ get_forecast + Redis cache + multi-turn chat | P1: carries demo |
| 4 (Sep 03) | 04 | SACHET alerts + FCM push + WebSocket | P2: carries demo |
| 5 (Sep 04) | 05 | Bhashini voice (ASR + TTS) + multilingual templates | P3: carries demo |
| 6 (Sep 05) | 06 | GFS/Zarr ingestion pipeline + DB models + Alembic | P4: meteorological score |
| 7 (Sep 06) | 07 | Docker Compose, polish, demo prep, final tests | Ship |
