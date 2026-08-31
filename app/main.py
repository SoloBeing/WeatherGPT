"""
WeatherGPT — FastAPI Application Entry Point

This is the main FastAPI application. It wires together:
- API routes (chat, weather queries, alerts, WebSocket)
- Startup/shutdown events (DB pool, Redis, MQTT subscriber)
- Middleware (CORS, request logging)

Run with: uvicorn app.main:app --reload
"""

from fastapi import FastAPI

app = FastAPI(
    title="WeatherGPT",
    description="Conversational AI for Weather Forecasting, Alerts, and Climate Information",
    version="0.1.0",
)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
