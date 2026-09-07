# WeatherGPT — Frontend Developer Handoff Guide 🌦️

Welcome to the **WeatherGPT** frontend integration guide! This reference is designed for frontend developers building user interfaces in React, Next.js, Vue, Svelte, or TypeScript.

---

## 📦 What's Prepared for You

1. **Pre-Generated TypeScript Types:** [`docs/weathergpt-types.ts`](./weathergpt-types.ts) (copy-paste directly into `src/types/weather.ts`)
2. **OpenAPI Specification:** [`docs/openapi.json`](./openapi.json) (compatible with Orval, RTK Query, or Swagger Editor)
3. **Automated Verification Script:** `uv run python scripts/demo.py` (simulates all backend subsystems and prints sample responses)
4. **CORS:** Enabled for all origins (`*`) — connect from any local frontend dev server (`localhost:3000`, `localhost:5173`, etc.)

---

## 🚀 1. Running the Backend Locally

### Option A: Local Python with Astral `uv` (Fastest)

```bash
# 1. Install dependencies
uv sync

# 2. Configure environment
cp .env.example .env

# 3. Start API server on port 8000 (hot reload enabled)
uv run uvicorn app.main:app --reload --port 8000
```

### Option B: Docker Compose (Full Stack)

```bash
docker compose up -d
```

- **API Base URL:** `http://localhost:8000`
- **Interactive Swagger Docs:** `http://localhost:8000/docs`
- **Health Diagnostics:** `http://localhost:8000/health`

---

## 📡 2. API Endpoints & Request/Response Contracts

---

### 2.1 Conversational Text Chat (`POST /chat`)

Sends a user text query and receives an intelligent, structured response backed by deterministic weather tools (GFS, Open-Meteo, IMD, SACHET).

- **Endpoint:** `POST http://localhost:8000/chat`
- **Headers:** `Content-Type: application/json`

#### Request Payload:
```json
{
  "message": "Will it rain in Bengaluru tomorrow?",
  "language": "en",
  "session_id": "123e4567-e89b-12d3-a456-426614174000"
}
```

- `message` (string, required): User's natural language weather or alert query.
- `language` (string, optional, default `"en"`): ISO 639-1 language code (`"en"`, `"hi"`, `"ta"`, `"te"`, `"bn"`, `"mr"`, etc.).
- `session_id` (string, optional): Pass the same UUID stored in `localStorage` across turns to maintain multi-turn memory.

#### Response Payload (`200 OK`):
```json
{
  "reply": "Currently in Bengaluru, it is 30.9°C with 58.9% humidity and wind around 20 km/h. Tomorrow expect light scattered rain.",
  "language": "en",
  "data": {
    "location_name": "Bengaluru, Karnataka, India",
    "lat": 12.9716,
    "lon": 77.5946,
    "temperature_c": 30.9,
    "feels_like_c": null,
    "humidity_pct": 58.9,
    "wind_speed_kmh": 20.0,
    "condition": "Light rain",
    "source": "NOAA GFS (0.25° NWP via Zarr - gfs_20260906_12z)"
  },
  "session_id": "123e4567-e89b-12d3-a456-426614174000",
  "sources": ["open-meteo", "gfs"]
}
```

> **UI Tip:** The `data` property contains the raw structured object returned by the weather tool. You can use it to render a temperature gauge or weather badge right below the chat message bubble!

---

### 2.2 Direct Weather & Forecast REST Endpoints (Non-Chat)

Use these to build dashboard widgets, graphs, and search bars without sending LLM chat turns.

#### A. Current Weather (`GET /weather/current`)
- **Query Params:** `location=Bengaluru` OR `lat=12.97&lon=77.59`
- **Response:**
```json
{
  "location_name": "Bengaluru, Bengaluru, India",
  "lat": 12.9716,
  "lon": 77.5946,
  "temperature_c": 30.9,
  "humidity_pct": 58.9,
  "wind_speed_kmh": 20.0,
  "condition": "Light rain",
  "source": "NOAA GFS (0.25° NWP via Zarr - gfs_20260906_12z)"
}
```

#### B. Multi-Day Forecast (`GET /weather/forecast`)
- **Query Params:** `location=Delhi&days=5&include_hourly=false`
- **Response:**
```json
{
  "location_name": "Delhi, Delhi, India",
  "lat": 28.61,
  "lon": 77.2,
  "daily": [
    {
      "date": "2026-09-06",
      "temp_max_c": 25.1,
      "temp_min_c": 23.9,
      "precipitation_mm": 0.0,
      "condition": "Partly cloudy"
    }
  ]
}
```

#### C. City Search / Autocomplete (`GET /weather/locations`)
- **Query Params:** `q=Mum&count=5`
- **Response:**
```json
[
  {
    "name": "Mumbai",
    "lat": 19.076,
    "lon": 72.8777,
    "country": "India",
    "country_code": "IN",
    "admin1": "Maharashtra",
    "confidence": 1.0
  }
]
```

---

### 2.3 Voice-to-Voice Chat (`POST /voice/chat`)

Full audio pipeline: User Audio In (ASR) ➔ Tool Calling ➔ Synthesized Audio Out (TTS).

- **Endpoint:** `POST http://localhost:8000/voice/chat`
- **Headers:** `Content-Type: multipart/form-data`

#### Multipart Form Data:
| Field | Type | Required | Description |
|---|---|---|---|
| `audio` | File / Blob | **Yes** | Recorded audio file (`webm`, `wav`, `mp3`, `ogg`, max 10MB) |
| `language` | String | No (default: `"hi"`) | ISO 639-1 source language code (e.g. `"hi"`, `"ta"`, `"te"`, `"en"`) |
| `response_format` | String | No (default: `"audio"`) | `"audio"` for TTS voice reply, `"text"` for text-only |
| `session_id` | String | No | Conversation session ID |

#### Response Payload (`200 OK`):
```json
{
  "transcript_in": "मुंबई में कल बारिश होगी क्या?",
  "reply_text": "मुंबई में कल: मध्यम वर्षा, तापमान 26°C से 30°C।",
  "reply_audio_base64": "UklGRi4AAABXQVZFZm10IBAAAAABAAEA...",
  "language": "hi",
  "session_id": "123e4567-e89b-12d3-a456-426614174000",
  "sources": ["open-meteo"]
}
```

#### Playing Voice Reply in Frontend:
```javascript
if (response.reply_audio_base64) {
  const audio = new Audio("data:audio/wav;base64," + response.reply_audio_base64);
  audio.play();
}
```

---

### 2.4 Supported Voice Languages (`GET /voice/languages`)

Populates the language selector dropdown in the UI with 23 supported Indian languages and dialects.

- **Endpoint:** `GET http://localhost:8000/voice/languages`

#### Response:
```json
{
  "languages": [
    {"code": "en", "name": "English"},
    {"code": "hi", "name": "Hindi"},
    {"code": "ta", "name": "Tamil"},
    {"code": "te", "name": "Telugu"},
    {"code": "bn", "name": "Bengali"},
    {"code": "mr", "name": "Marathi"},
    {"code": "gu", "name": "Gujarati"},
    {"code": "kn", "name": "Kannada"},
    {"code": "ml", "name": "Malayalam"},
    {"code": "or", "name": "Odia"},
    {"code": "pa", "name": "Punjabi"},
    {"code": "as", "name": "Assamese"},
    {"code": "ur", "name": "Urdu"},
    {"code": "sa", "name": "Sanskrit"}
  ],
  "count": 23
}
```

---

### 2.5 Real-Time Disaster Alerts & WebSocket

#### A. Direct Alert Lookup (`GET /alerts`)
- **Query Params:** `location=Chennai` (or `lat=13.08&lon=80.27`)
- **Response:**
```json
{
  "location_name": "Chennai, Tamil Nadu, India",
  "lat": 13.0827,
  "lon": 80.2707,
  "count": 0,
  "alerts": []
}
```

#### B. Active Nationwide Alerts (`GET /alerts/active`)
Returns all active NDMA SACHET and IMD disaster warnings currently monitored across India.

#### C. Live WebSocket Stream (`WS /ws/alerts`)
Connect your frontend to `ws://localhost:8000/ws/alerts` to receive push events for active and incoming emergency warnings.

##### Connection Handshake & Lifecycle:
1. **Initial Snapshot (`type: "init"`):** Immediately upon connection, the server sends the current active alert snapshot:
   ```json
   {
     "type": "init",
     "timestamp": "2026-09-07T14:30:00Z",
     "active_alerts_count": 2,
     "alerts": [ /* array of active AlertRecord objects */ ]
   }
   ```
2. **Real-Time Broadcast (`type: "weather_alert"`):** Whenever NDMA SACHET or IMD issues a new Severe or Extreme warning, it is broadcast live:
   ```json
   {
     "type": "weather_alert",
     "timestamp": "2026-09-07T14:35:12Z",
     "alert": {
       "alert_id": "NDMA-2026-09-07-001",
       "event": "Very Severe Cyclonic Storm",
       "severity": "Extreme",
       "headline": "Red Alert: Cyclonic storm approaching coast",
       "instruction": "Evacuate low-lying areas and remain indoors."
     }
   }
   ```

##### Frontend Integration Example:
```javascript
const ws = new WebSocket("ws://localhost:8000/ws/alerts");

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  if (msg.type === "init") {
    console.log(`Loaded initial snapshot of ${msg.active_alerts_count} active disaster alerts.`);
    // Render initial alert ticker / badge count
  } else if (msg.type === "weather_alert") {
    console.warn("🚨 Real-time Emergency Alert Received:", msg.alert.headline);
    // Trigger audio chime & show emergency toast / banner
  }
};
```

---

### 2.6 SIH Multi-Domain Weather Modules (Chat & Tools)

WeatherGPT includes dedicated meteorological engines for all key SIH domains:

| Domain | Underlying Engine | Tool Name | Key Data Returned in `ChatResponse.data` |
|---|---|---|---|
| **Marine & Fishery** | Open-Meteo Marine + INCOIS | `get_marine_weather` | `MarinePoint` (sea state, wave height, swell, ocean currents, SST, PFZ advisory) |
| **Aviation** | NOAA Aviation Weather Center | `get_aviation_weather` | `AviationWeather` (flight category VFR/IFR, decoded METAR, crosswinds, runway visibility) |
| **Agriculture** | ICAR / IMD Agromet Engine | `get_agricultural_advisory` | `CropAdvisoryReport` (phenology stage, irrigation timing, spray windows, pest risks) |
| **Historical Climate** | ECMWF ERA5 Reanalysis | `get_climatology` | `ClimatologyReport` (WMO 30-year normal, decadal warming trend, anomalies, monthly normals) |
| **NWP Forecasting** | NOAA GFS 0.25° Zarr Store | `get_current_weather`, `get_forecast` | `ForecastPoint`, `ForecastTimeline` (with `data_quality: "verified"` or `"synthetic"`) |

---

### 2.7 Health Check & Diagnostics (`GET /health`)

- **Endpoint:** `GET http://localhost:8000/health`
- **Response (`200 OK`):**
```json
{
  "status": "ok", // "ok" if database & redis are healthy, "degraded" if running offline/sandbox
  "database": "connected",
  "redis": "connected",
  "scheduler_running": true
}
```

---

## 🎨 3. Recommended UI Components & Integration Flow

1. **Header Bar:**
   - **Language Dropdown:** Populated dynamically via `GET /voice/languages` (defaults to `"en"` or `"hi"`).
   - **Location Autocomplete Bar:** Debounced input calling `GET /weather/locations?q=...`.
   - **Disaster Alert Toast:** Listens on `ws://localhost:8000/ws/alerts` or queries `GET /alerts?location=...`.

2. **Main Dashboard / Chat Area:**
   - Text chat with message history.
   - For every assistant reply, check if `response.data` is present:
     - If it contains `temperature_c` and `condition`: Render a mini weather card with temperature, humidity, wind, and data source badge.
     - If it contains `daily`: Render a multi-day forecast chart/cards.

3. **Push-to-Talk Voice Button:**
   - Standard browser `navigator.mediaDevices.getUserMedia({ audio: true })`.
   - Use `MediaRecorder` with `audio/webm` or `audio/wav`.
   - Append to `FormData` and POST to `/voice/chat`.
   - On response, automatically trigger audio playback if `reply_audio_base64` exists.
