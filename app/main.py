"""
WeatherGPT — FastAPI Application Entry Point

This is the main FastAPI application. It wires together:
- API routes (chat, weather queries, alerts, WebSocket)
- Startup/shutdown events (DB pool, Redis, MQTT subscriber)
- Middleware (CORS, request logging)

Run with: uvicorn app.main:app --reload
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api_gateway.routes.chat import router as chat_router
from app.api_gateway.routes.voice import router as voice_router
from app.api_gateway.routes.websocket import router as ws_router
from app.config import settings

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="WeatherGPT",
    description="Conversational AI for Weather Forecasting, Alerts, and Climate Information",
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

app.include_router(chat_router)
app.include_router(voice_router)
app.include_router(ws_router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Startup / Shutdown
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup():
    logger.info("🚀 WeatherGPT starting up — model=%s", settings.LLM_MODEL)


@app.on_event("shutdown")
async def shutdown():
    logger.info("🛑 WeatherGPT shutting down")
