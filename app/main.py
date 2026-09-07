"""
WeatherGPT — FastAPI Application Entry Point

This is the main FastAPI application. It wires together:
- API routes (chat, weather queries, alerts, WebSocket)
- Startup/shutdown events (DB pool, Redis, MQTT subscriber)
- Middleware (CORS, request logging)

Run with: uvicorn app.main:app --reload
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.alerts import router as alerts_router
from app.api.routes.chat import router as chat_router
from app.api.routes.voice import router as voice_router
from app.api.routes.weather import router as weather_router
from app.api.routes.websocket import router as ws_router
from app.config import settings
from app.pipelines.scheduler import ingestion_scheduler


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
# Lifespan Context Manager
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Modern async lifespan context manager managing startup and shutdown."""
    logger.info("🚀 WeatherGPT starting up — model=%s", settings.LLM_MODEL)
    try:
        ingestion_scheduler.start()
    except Exception as exc:
        logger.error("Failed to start ingestion scheduler: %s", exc)

    yield

    logger.info("🛑 WeatherGPT shutting down")
    from app.data_sources.gfs import gfs_client
    from app.data_sources.openmeteo import openmeteo_client
    from app.database import cache, close_db
    from app.services.bhashini import bhashini_service
    from app.pipelines.sachet_poller import sachet_poller

    try:
        ingestion_scheduler.shutdown()
    except Exception as exc:
        logger.debug("Error shutting down scheduler: %s", exc)

    try:
        await close_db()
    except Exception as exc:
        logger.debug("Error closing DB: %s", exc)

    try:
        await cache.close()
    except Exception as exc:
        logger.debug("Error closing Redis: %s", exc)

    try:
        await sachet_poller.close()
    except Exception as exc:
        logger.debug("Error closing SACHET poller: %s", exc)

    try:
        await openmeteo_client.close()
    except Exception as exc:
        logger.debug("Error closing Open-Meteo client: %s", exc)

    try:
        await bhashini_service.close()
    except Exception as exc:
        logger.debug("Error closing Bhashini service: %s", exc)

    from app.tools.location_resolver import close_geocoder

    try:
        await close_geocoder()
    except Exception as exc:
        logger.debug("Error closing geocoder client: %s", exc)

    try:
        await gfs_client.close()
    except Exception as exc:
        logger.debug("Error closing GFS client: %s", exc)

    from app.data_sources.incois import incois_client

    try:
        await incois_client.close()
    except Exception as exc:
        logger.debug("Error closing INCOIS client: %s", exc)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="WeatherGPT",
    description="Conversational AI for Weather Forecasting, Alerts, and Climate Information",
    version="0.1.0",
    lifespan=lifespan,
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
app.include_router(weather_router)
app.include_router(alerts_router)



@app.get("/health")
async def health_check():
    """Health check endpoint with subsystem status."""
    from app.database import cache, check_db_health

    db_healthy = await check_db_health()
    redis_healthy = await cache.ping()

    return {
        "status": "ok",
        "database": "connected" if db_healthy else "disconnected",
        "redis": "connected" if redis_healthy else "disconnected",
        "scheduler_running": ingestion_scheduler._is_running,
    }

