"""
WebSocket Route — Real-time push to browser and mobile clients.

The spec says: MQTT in (WIS2.0), WebSocket out (browser).
This endpoint pushes live alert updates and forecast refreshes
to connected frontend clients.
"""

from datetime import datetime, timezone
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.ingestion_pipelines.sachet_poller import sachet_poller
from app.models.schemas import AlertRecord

logger = logging.getLogger(__name__)

router = APIRouter(tags=["realtime"])


class ConnectionManager:
    """Manages real-time WebSocket client connections and broadcasts."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """Accept new WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("WebSocket client connected. Total active: %d", len(self.active_connections))

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove disconnected WebSocket."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info("WebSocket client disconnected. Total active: %d", len(self.active_connections))

    async def broadcast_json(self, message: dict[str, Any]) -> None:
        """Broadcast JSON payload to all connected clients."""
        disconnected: list[WebSocket] = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning("Failed to send to WebSocket client: %s", e)
                disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(conn)

    async def broadcast_alert(self, alert: AlertRecord) -> None:
        """Format and broadcast an AlertRecord to all active clients."""
        payload = {
            "type": "weather_alert",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "alert": json.loads(alert.model_dump_json(exclude_none=True)),
        }
        logger.info("Broadcasting alert [%s] to %d WebSocket clients", alert.alert_id, len(self.active_connections))
        await self.broadcast_json(payload)


ws_manager = ConnectionManager()

# Register WebSocket broadcaster with SACHET poller
sachet_poller.register_listener(ws_manager.broadcast_alert)


@router.websocket("/ws/alerts")
async def websocket_alerts_endpoint(websocket: WebSocket) -> None:
    """Real-time WebSocket feed for live weather and disaster alerts.

    Upon connection, sends active alert snapshot.
    Pushes new alerts in real-time as they arrive from SACHET/IMD.
    """
    await ws_manager.connect(websocket)

    # Send initial snapshot of currently active alerts
    active_alerts = sachet_poller.get_all_active()
    await websocket.send_json({
        "type": "init",
        "message": "Connected to WeatherGPT Realtime Alert Stream",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "active_alerts_count": len(active_alerts),
        "alerts": [json.loads(a.model_dump_json(exclude_none=True)) for a in active_alerts],
    })

    try:
        while True:
            # Client heartbeats or filter commands
            data = await websocket.receive_text()
            if data.strip().lower() == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error("WebSocket connection exception: %s", e)
        ws_manager.disconnect(websocket)

