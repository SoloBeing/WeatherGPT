# WeatherGPT — Frontend Developer Handoff Guide 🌦️

This guide contains everything you need to connect your frontend application (React, Next.js, Vue, Svelte, or vanilla JS/TS) to the **WeatherGPT** backend.

---

## 🚀 1. Running the Backend Locally

### Option A: Local Python with Astral `uv` (Fastest)

```bash
# 1. Install/sync dependencies into virtualenv
uv sync

# 2. Configure environment (defaults work out of the box for testing)
cp .env.example .env

# 3. Start API server on port 8000 with hot-reload
uv run uvicorn app.main:app --reload --port 8000
```

### Option B: Docker Compose (Full Stack)

```bash
# Starts PostgreSQL + PostGIS, Redis, MinIO, Migrations, Worker, and API
docker compose up -d
```

- **Base URL:** `http://localhost:8000`
- **Interactive Swagger Docs:** `http://localhost:8000/docs`
- **Health Diagnostics:** `http://localhost:8000/health`
- **Automated Verification Script:** `uv run python scripts/demo.py`

> **Note on CORS:** CORS is enabled for all origins (`*`) by default, so your frontend can connect directly from `http://localhost:3000`, `http://localhost:5173`, etc.

---

## 📡 2. Core API Contracts

### 2.1 Conversational Text Chat (`POST /chat`)

Sends a user text query and receives an intelligent, structured response backed by deterministic weather tools (GFS, Open-Meteo, IMD, SACHET).

- **Endpoint:** `POST http://localhost:8000/chat`
- **Headers:** `Content-Type: application/json`

#### Request Payload:
```json
{
  "message": "Will it rain in Bengaluru tomorrow?",
  "language": "en",
  "session_id": "optional-uuid-string"
}
```

- `message` (string, required): User's natural language weather or alert query.
- `language` (string, optional, default `"en"`): ISO 639-1 language code (`"en"`, `"hi"`, `"ta"`, `"te"`, `"bn"`, `"mr"`, etc.).
- `session_id` (string, optional): A unique ID (e.g. UUID stored in `localStorage`). Pass the same `session_id` across turns to maintain conversation context.

#### Response Payload (`200 OK`):
```json
{
  "reply": "Currently in Bengaluru, it is 28.5°C with 58% humidity. Tomorrow expects light scattered rain with max temperatures around 29°C.",
  "language": "en",
  "data": null,
  "session_id": "optional-uuid-string",
  "sources": ["open-meteo", "gfs"]
}
```

---

### 2.2 Voice-to-Voice Chat (`POST /voice/chat`)

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
  "session_id": "optional-uuid-string",
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

### 2.3 Supported Voice Languages (`GET /voice/languages`)

Populates the language selector dropdown in the UI with 23 supported Indian languages and dialects.

- **Endpoint:** `GET http://localhost:8000/voice/languages`

#### Response Payload (`200 OK`):
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

### 2.4 Real-Time Disaster Alerts WebSocket (`WS /ws/alerts`)

Push notification channel for live NDMA SACHET / IMD CAP disaster alerts.

- **WebSocket URL:** `ws://localhost:8000/ws/alerts`

#### Incoming JSON Message:
```json
{
  "type": "weather_alert",
  "timestamp": "2026-09-06T14:20:00.000Z",
  "alert": {
    "alert_id": "IN-MD-2026-0012",
    "source": "sachet-ndma",
    "sender": "IMD",
    "event": "Heavy Rainfall",
    "severity": "Severe",
    "headline": "Severe rainfall warning for coastal districts",
    "description": "Localized flooding and gusty winds likely in coastal areas.",
    "instruction": "Avoid low-lying areas. Fishermen advised not to venture into sea.",
    "area_desc": "Chennai, Kanchipuram, Tiruvallur"
  }
}
```

#### Frontend WebSocket Hook Example (React):
```typescript
import { useEffect, useState } from "react";

export function useAlertWebSocket() {
  const [activeAlert, setActiveAlert] = useState<any>(null);

  useEffect(() => {
    const ws = new WebSocket("ws://localhost:8000/ws/alerts");

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "weather_alert") {
          setActiveAlert(data.alert);
        }
      } catch (err) {
        console.error("Failed to parse alert websocket event", err);
      }
    };

    ws.onerror = (err) => console.error("Alerts WS error:", err);
    return () => ws.close();
  }, []);

  return activeAlert;
}
```

---

### 2.5 Health Check & Diagnostics (`GET /health`)

- **Endpoint:** `GET http://localhost:8000/health`

#### Response:
```json
{
  "status": "ok",
  "database": "connected",
  "redis": "connected",
  "scheduler_running": true
}
```

---

## 🎨 3. Recommended Frontend UI Layout

1. **Top Bar:**
   - App Logo & Title: **WeatherGPT 🌦️**
   - Active Disaster Banner (hidden if no alerts; Red/Orange/Yellow toast if an alert arrives via WebSocket)
   - Language Selector dropdown (populated via `GET /voice/languages`)
   - Backend Connection status dot (green when `/health` returns `status: "ok"`)

2. **Chat Area:**
   - Multi-turn conversation history
   - Assistant bubbles showing weather responses with data provider badges (`Open-Meteo`, `NOAA GFS`, `NDMA SACHET`)
   - Optional audio replay button for voice responses

3. **Input Bar:**
   - Text input field with send button
   - **Voice Recording Button (Push-to-Talk):**
     - Hold or click to record using Web `MediaRecorder` API
     - Sends audio blob to `POST /voice/chat`
     - Plays back returned base64 audio automatically
