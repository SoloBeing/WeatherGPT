# api — Context

## Role
FastAPI route handlers and dependency injection. This is the HTTP boundary layer.

## Files
- `deps.py` — DI providers: DB session, Redis client, settings
- `routes/chat.py` — Primary conversational endpoint (text in → response out)
- `routes/weather.py` — Direct REST endpoints bypassing LLM (programmatic access)
- `routes/alerts.py` — Alert queries + push subscription registration
- `routes/websocket.py` — Real-time push (MQTT in → WebSocket out to browser)

## Rules
- Routes are thin — no business logic here, delegate to core or tools
- All routes are async
- Use dependency injection from deps.py for DB/Redis/settings
- Stream tokens to client so first-token is <500ms
