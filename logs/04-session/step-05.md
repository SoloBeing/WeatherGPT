# Session 04 — Step 05: WebSocket Live Alert Streaming Endpoint

**Date:** 2026-09-01  
**Goal:** Implement WebSocket `/ws/alerts` endpoint and broadcast newly ingested CAP alerts to connected frontend clients.

## What was done

1. **Implemented `app/api_gateway/routes/websocket.py`**:
   - `ConnectionManager`: Handles connected clients list, safe JSON broadcast, and `broadcast_alert(alert: AlertRecord)`.
   - Registered `ws_manager.broadcast_alert` as an async listener with `SachetPoller`.
   - `websocket_alerts_endpoint` on `/ws/alerts`: Sends active alert snapshot on connection and handles client heartbeats.

2. **Updated `app/main.py`**:
   - Included `ws_router` in the FastAPI application.

## Exact commands & verification

```bash
uv run python -c "
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
with client.websocket_connect('/ws/alerts') as websocket:
    data = websocket.receive_json()
    print('WS Init type:', data['type'])
    print('WS Active alerts count:', data['active_alerts_count'])
    websocket.send_text('ping')
    ack = websocket.receive_text()
    print('WS Ping ack:', ack)
"
```

## Notable output

```
WS Init type: init
WS Active alerts count: 3
WS Ping ack: pong
```

## Files changed

- `IMPL app/api_gateway/routes/websocket.py`
- `MOD  app/main.py`
