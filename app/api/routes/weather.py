"""
Weather Routes — Direct REST endpoints for programmatic weather queries.

Provides structured endpoints for frontend widgets, cards, and graphs:
  - GET /weather/current?location=... (or ?lat=...&lon=...)
  - GET /weather/forecast?location=...&days=5
  - GET /weather/locations?q=... (autocomplete / geocoding)
"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import ForecastPoint, ForecastTimeline, LocationMatch
from app.tools.current import get_current_weather
from app.tools.forecast import get_forecast
from app.tools.location_resolver import resolve_location

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/weather", tags=["weather"])


@router.get("/current", response_model=dict)
async def get_current_weather_endpoint(
    location: Optional[str] = Query(None, description="City or place name (e.g. 'Mumbai', 'Delhi')"),
    lat: Optional[float] = Query(None, ge=-90.0, le=90.0, description="Latitude coordinate"),
    lon: Optional[float] = Query(None, ge=-180.0, le=180.0, description="Longitude coordinate"),
) -> dict:
    """Retrieve structured current weather conditions for a named location or coordinates."""
    query_loc = location
    if not query_loc:
        if lat is not None and lon is not None:
            query_loc = f"{lat},{lon}"
        else:
            raise HTTPException(
                status_code=400,
                detail="Either 'location' name or both 'lat' and 'lon' coordinates must be provided.",
            )

    try:
        raw_json = await get_current_weather(query_loc)
        data = json.loads(raw_json)
        if "error" in data:
            raise HTTPException(status_code=404, detail=data["error"])
        return data
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to fetch current weather for %s: %s", query_loc, exc)
        raise HTTPException(status_code=500, detail=f"Weather service error: {exc}") from exc


@router.get("/forecast", response_model=dict)
async def get_forecast_endpoint(
    location: Optional[str] = Query(None, description="City or place name (e.g. 'Bengaluru')"),
    lat: Optional[float] = Query(None, ge=-90.0, le=90.0, description="Latitude coordinate"),
    lon: Optional[float] = Query(None, ge=-180.0, le=180.0, description="Longitude coordinate"),
    days: int = Query(5, ge=1, le=16, description="Forecast horizon in days (1-16)"),
    include_hourly: bool = Query(False, description="Include hourly forecast breakdown"),
) -> dict:
    """Retrieve structured multi-day weather forecast timeline."""
    query_loc = location
    if not query_loc:
        if lat is not None and lon is not None:
            query_loc = f"{lat},{lon}"
        else:
            raise HTTPException(
                status_code=400,
                detail="Either 'location' name or both 'lat' and 'lon' coordinates must be provided.",
            )

    try:
        raw_json = await get_forecast(location=query_loc, days=days, include_hourly=include_hourly)
        data = json.loads(raw_json)
        if "error" in data:
            raise HTTPException(status_code=404, detail=data["error"])
        return data
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to fetch forecast for %s: %s", query_loc, exc)
        raise HTTPException(status_code=500, detail=f"Forecast service error: {exc}") from exc


@router.get("/locations", response_model=list[LocationMatch])
async def search_locations_endpoint(
    q: str = Query(..., min_length=2, description="Search query for Indian cities, towns, or states"),
    count: int = Query(5, ge=1, le=20, description="Maximum number of suggestions to return"),
) -> list[LocationMatch]:
    """Search and autocomplete locations across India with gazetteer and geocoding."""
    try:
        return await resolve_location(name=q, count=count)
    except Exception as exc:
        logger.exception("Location search failed for '%s': %s", q, exc)
        raise HTTPException(status_code=500, detail=f"Location resolution error: {exc}") from exc
