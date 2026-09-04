# Session 05 — Step 05: Wire Voice Router + Expand Multilingual Templates

**What was done:**
1. **Wired voice router** into `app/main.py`:
   - `from app.api_gateway.routes.voice import router as voice_router`
   - `app.include_router(voice_router)`
   - New endpoints: `POST /voice/chat`, `GET /voice/languages`

2. **Expanded templates** from 2 languages → 6 in `app/llm_orchestrator/templates.py`:
   - English (`en`) — existing
   - Hindi (`hi`) — existing
   - Tamil (`ta`) — NEW: current weather + forecast + alerts
   - Telugu (`te`) — NEW: current weather + forecast + alerts
   - Bengali (`bn`) — NEW: current weather + forecast + alerts
   - Marathi (`mr`) — NEW: current weather + forecast + alerts

3. **Refactored template selection** from if/else chains to dict-based registry:
   - `_CURRENT_WEATHER_TEMPLATES`, `_DAILY_ITEM_TEMPLATES` — template string lookup
   - `_RAIN_CHANCE_FMT`, `_PRECIP_FMT` — rain info format strings
   - `_FORECAST_HEADER`, `_NO_ALERTS`, `_ALERTS_HEADER` — header/status strings
   - `_UNKNOWN_LABELS` — "Unknown" in each language
   - All functions fall back to English for unsupported language codes

**Design decisions:**
- Registry-based lookup is extensible — add a new language by adding 6 dict entries
- All templates use verified native-script strings (not LLM-generated translations)
- Alert detail lines (headline, description, instruction) stay in English — they come from SACHET/IMD XML and are pre-authored by the issuing agency
