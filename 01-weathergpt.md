# WeatherGPT: Conversational AI for Weather Forecasting, Alerts, and Climate Information

Short version: **the LLM never computes or recalls weather.** It only (a) parses the query into a structured intent, (b) calls tools, (c) phrases the tool output in the user's language. Every number comes from a deterministic service. Get that boundary right and "accuracy and relevance" scores itself; get it wrong and it hallucinates rainfall figures on stage.

Everything below hangs off that.

---

## Tech stack

| Layer            | Pick                                  | Why                                                      |
|------------------|---------------------------------------|----------------------------------------------------------|
| Mobile           | Flutter                               | One codebase, good offline cache, native TTS/STT plugins |
| API gateway      | FastAPI (Python 3.11+)                | Async, matches the scientific stack below                |
| Orchestrator     | LLM with native tool-calling          | Router + phraser, not a knowledge source                 |
| Small/fast model | Haiku-class or Llama-3.1-8B local     | Intent classification, ~100ms, cheap                     |
| Big model        | Any frontier tool-calling model       | Only for multi-step reasoning + synthesis                |
| Grid data        | `xarray` + `zarr` + `cfgrib`          | GRIB2 → chunked arrays, point queries in ms              |
| GRIB fetch       | `herbie` / `ecmwf-opendata`           | Handles NOMADS + AWS mirrors, retries, subsetting        |
| Geospatial       | PostGIS + TimescaleDB (one Postgres)  | Alert polygons + station timeseries in one DB            |
| Object store     | MinIO / S3                            | Zarr stores, COGs, satellite tiles                       |
| Cache            | Redis                                 | Point forecasts (TTL 1h), semantic query cache           |
| Ingestion        | Prefect (or APScheduler if time-poor) | GFS cycles are cron-shaped; Airflow is overkill          |
| Realtime         | MQTT (paho) in, WebSocket out         | WIS2.0 is MQTT; browser needs WS                         |
| Push             | Firebase Cloud Messaging              | Alert fan-out to devices                                 |
| Map tiles        | TiTiler + MapLibre GL                 | Serve COGs directly, no pre-tiling                       |
| Voice + langs    | Bhashini (ULCA) APIs                  | Govt-backed, 22 languages, ASR+MT+TTS                    |
| Deploy           | Docker Compose → K8s manifest         | Compose for the demo, manifests to claim scalability     |

Skip MongoDB. Postgres with `JSONB` covers the document case and you avoid running two databases.

---

## Where the data comes from

**Forecasts and current conditions**

| Source           | Access                              | Gives you                                   |
|------------------|-------------------------------------|---------------------------------------------|
| Open-Meteo       | No key, free, REST                  | GFS/ECMWF/ICON blended, hourly, 16-day      |
| NOAA GFS         | `s3://noaa-gfs-bdp-pds`, anon       | Raw 0.25° GRIB2, 4 cycles/day, 384h         |
| ECMWF Open Data  | `ecmwf-opendata` pkg                | IFS 0.25°, better skill than GFS            |
| IMD Mausam       | JSON endpoints on mausam.imd.gov.in | Official Indian city obs + district warnings |
| Open-Meteo Flood | No key                              | GloFAS river discharge — flood use case     |

**Alerts**

| Source                | Access                            | Gives you                                      |
|-----------------------|-----------------------------------|------------------------------------------------|
| NDMA SACHET           | CAP-XML feed                      | India's official CAP alerts, with polygons     |
| IMD district warnings | JSON                              | Colour-coded (green/yellow/orange/red) nowcasts |
| WIS2.0 Global Broker  | MQTTS `globalbroker.meteo.fr:8883` | Live push notifications, `everyone/everyone`   |

**Historical and climate**

| Source        | Access                     | Gives you                                          |
|---------------|----------------------------|----------------------------------------------------|
| ERA5 via CDS  | `cdsapi`, free registration | 1940→present reanalysis, the climate-trend backbone |
| NASA POWER    | No key, REST               | Daily agromet params, 1981→present, point-based    |
| IMD Pune DSP  | Registration, some paid    | Gridded India rainfall/temp, 0.25°, 1901→          |
| MOSDAC (ISRO) | Registration               | INSAT-3D/3DR satellite, rainfall, cloud imagery    |

Verify the IMD `mausam.imd.gov.in/api/*` endpoints yourself before demo day — they're undocumented, unversioned, and occasionally move. Always have Open-Meteo as the fallback behind the same internal interface.

**WRF**: don't run it live. Run one nested domain (India 12km → your district 4km) initialised from GFS ahead of time, store the output as Zarr, and query it like any other source. Live WRF is hours of compute you don't have.

---

## Wiring it up

**Ingestion (runs on its own clock, never in the request path)**

```
GFS cycle lands on S3 (00/06/12/18Z)
  → Prefect flow triggers ~3.5h after cycle time
  → herbie downloads subset (India bbox, ~12 variables)
  → cfgrib → xarray → write Zarr to MinIO
  → register cycle in Postgres (model, run_time, valid_range, path)

WIS2 MQTT subscriber (long-running)
  → topic origin/a/wis2/#, filter India centres
  → notification carries a canonical URL → fetch payload
  → parse → Postgres

SACHET CAP poller (60s)
  → parse CAP-XML → alert row with PostGIS geometry
  → ST_Intersects against user_locations
  → matched users → FCM push + WebSocket broadcast
```

**Request path**

```
Voice/text  →  Bhashini ASR  →  text (native script)
            →  intent classifier (small model)
                  ├─ needs numbers?  → tool call
                  └─ chit-chat/definition → RAG over IMD docs
            →  tool layer  ──┬─ get_current(lat,lon)
                             ├─ get_forecast(lat,lon,hours)
                             ├─ get_alerts(geom)
                             ├─ get_climatology(lat,lon,var,years)
                             └─ get_advisory(crop,stage,forecast)
            →  each tool: Redis  →  Zarr/Postgres  →  external API
            →  structured JSON result
            →  big model: phrase it (JSON in, prose out, temp 0.2)
            →  Bhashini TTS  →  audio
```

The tool layer is where you enforce a single internal schema. Every source — IMD, Open-Meteo, GFS, WRF — normalises to the same `ForecastPoint` object with a `source` and `issued_at` field. Then swapping sources is a config change, and you can cite provenance in the answer ("per IMD, issued 08:30 IST"), which reads as rigour to judges.

**Location resolution** deserves its own tool. Indian place names are ambiguous and voice input mangles them. Build a gazetteer table (village/town/district, ~600k rows from LGD or GeoNames) with `pg_trgm` fuzzy matching, and resolve *before* the LLM sees the query. Ask a disambiguating question when confidence is low.

---

## Multilingual, done safely

Don't translate free-form LLM prose — errors compound and you can't audit them. Instead:

1. Tools return structured values.
2. Fill a **template** per language for the factual core: `"{district} में कल {rain_mm} मिमी बारिश की संभावना है"`.
3. Use the LLM only for the surrounding conversational glue.

Templates are verifiable, instant, and never invent a number. Bhashini's NMT handles anything template coverage misses. AI4Bharat's IndicTrans2 and IndicConformer are the self-hosted fallback if Bhashini rate-limits you.

---

## Hitting the other scoring parameters

- **Latency**: intent classification on the small model, Redis on every point query, stream tokens to the client so first-token is <500ms. Precompute forecasts for the top 5000 Indian towns after each GFS cycle — most queries then never touch a Zarr read.
- **Scalability**: stateless FastAPI pods, ingestion as separate deployments, Postgres read replica. Show the K8s manifests and an HPA — that's the claim, cheaply.
- **Innovation**: proactive alerts are the strongest card. Everyone builds a query-response bot; a bot that *pushes* "cyclone track shifted, your taluk is now in the orange zone" via the CAP → PostGIS → FCM chain demonstrates real integration.
- **Accessibility**: voice-first UI with a big push-to-talk button, SMS fallback via an SMS gateway for feature phones, and cached last-known forecast rendered offline.

---

If you're time-boxed, build in this order: FastAPI + Open-Meteo + one tool + text chat → SACHET alerts + push → Bhashini voice → GFS/Zarr pipeline → WRF. The first three carry the demo; the last two carry the "integration with real-time meteorological systems" score.
