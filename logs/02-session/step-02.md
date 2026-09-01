# Session 02 — Step 02: Weather Tool + LLM Orchestrator + API Wiring

**Date:** 2026-09-01  
**Goal:** Implement the remaining layers and achieve end-to-end chat

## What was done

### Weather Tool — `app/weather_tools/current.py`
- Implemented `get_current_weather(location: str) -> str`
- Flow: resolve location → fetch Open-Meteo → return JSON string
- Returns `ForecastPoint.model_dump_json(exclude_none=True)` for clean LLM input
- Error handling for both location resolution and weather fetch failures

### Response Templates — `app/llm_orchestrator/templates.py`
- English + Hindi templates for current weather
- `format_current_weather(point, language)` fills verified templates
- Factual core is template-driven — no LLM involved in the numbers

### LLM Orchestrator — `app/llm_orchestrator/router.py`
- System prompt enforcing "LLM never computes weather" boundary
- Tool definitions in OpenAI function-calling format (used by litellm)
- `_TOOL_DISPATCH` map: tool name → async callable
- Async tool-calling loop with `_MAX_TOOL_ROUNDS = 5` safety limit
- `chat(message, language) -> ChatResponse`

### API Layer
- `app/api_gateway/deps.py` — `get_settings()` dependency
- `app/api_gateway/routes/chat.py` — `POST /chat` endpoint
- `app/main.py` — CORS middleware, chat router, startup/shutdown logging

### Groq Model Config
- **Issue:** `llama-3.3-70b-versatile` no longer available on Groq
- **Fix:** Queried `https://api.groq.com/openai/v1/models` for current models
- **Final config:**
  - `LLM_MODEL=groq/openai/gpt-oss-120b` (main model)
  - `INTENT_MODEL=groq/qwen/qwen3.8-27b` (fast/intent)

## Smoke test results

```bash
# Health check
curl -s http://localhost:8000/health
# → {"status": "ok"}

# English weather query
curl -s -X POST http://localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"message": "What is the weather in Delhi?"}'
# → 28°C, mainly clear, 83% humidity (real Open-Meteo data)

# Hindi query (Hinglish input)
curl -s -X POST http://localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"message": "Jaipur mein mausam kaisa hai?"}'
# → Responded in Hindi! 28°C, partly cloudy (real data)

# Chit-chat (no tool call)
curl -s -X POST http://localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"message": "Hello! Who are you?"}'
# → Greeting response, no tool calls, sources=[]
```

## Files changed
- `IMPL app/weather_tools/current.py`
- `IMPL app/llm_orchestrator/templates.py`
- `IMPL app/llm_orchestrator/router.py`
- `IMPL app/api_gateway/deps.py`
- `IMPL app/api_gateway/routes/chat.py`
- `IMPL app/main.py`
- `FIX  .env` — updated model names to available Groq models
