"""
get_forecast(location, days) — Multi-day and hourly weather forecasts.

Returns: Daily forecast summaries (temperature ranges, precipitation, rain probability, wind, UV, weather conditions).
Checks Redis cache first (TTL 1h), then Open-Meteo fallback.
"""

import json
import logging

from app.database.redis_cache import cache
from app.data_sources.openmeteo import OpenMeteoClient
from app.weather_tools.location_resolver import resolve_location

logger = logging.getLogger(__name__)


async def get_forecast(location: str, days: int = 5, include_hourly: bool = False) -> str:
    """Get multi-day weather forecast for a named location.

    This is the tool function called by the LLM orchestrator.

    Flow:
        1. Resolve location name → lat/lon (Open-Meteo geocoding)
        2. Check Redis cache first (TTL 1h)
        3. If cache miss, fetch forecast → ForecastTimeline (Open-Meteo)
        4. Populate cache and return JSON string for LLM consumption

    Args:
        location: City or place name (e.g. "Delhi", "Mumbai", "Jaipur").
        days: Number of days to forecast (1 to 16, default 5).
        include_hourly: Whether to include hourly breakdown (default False).

    Returns:
        JSON string with forecast timeline or error message.
    """
    days = max(1, min(days, 16))

    # Step 1: Resolve location name to coordinates
    try:
        matches = await resolve_location(location)
    except Exception as e:
        logger.error("Location resolution failed for '%s': %s", location, e)
        return json.dumps({"error": f"Could not resolve location: {location}. {e}"})

    if not matches:
        return json.dumps({
            "error": f"Could not find location: '{location}'. Try a more specific name."
        })

    best = matches[0]
    location_display = best.name
    if best.admin1:
        location_display += f", {best.admin1}"
    if best.country:
        location_display += f", {best.country}"

    # Step 2: Check cache
    cached_data = await cache.get_forecast(best.lat, best.lon, days)
    if cached_data:
        logger.info("Cache HIT for forecast at %s (%.4f, %.4f, days=%d)", location_display, best.lat, best.lon, days)
        return cached_data

    logger.debug("Cache MISS for forecast at %s (%.4f, %.4f, days=%d)", location_display, best.lat, best.lon, days)

    # Step 3: Fetch forecast from Open-Meteo
    client = OpenMeteoClient()
    try:
        timeline = await client.fetch_forecast(best.lat, best.lon, days=days, include_hourly=include_hourly)
        timeline.location_name = location_display
    except Exception as e:
        logger.error("Forecast fetch failed for %s (%.4f, %.4f): %s", location, best.lat, best.lon, e)
        return json.dumps({"error": f"Forecast data unavailable for {location}. {e}"})
    finally:
        await client.close()

    logger.info(
        "Forecast for %s: %d days retrieved",
        location_display,
        len(timeline.daily),
    )

    data_json = timeline.model_dump_json(exclude_none=True)

    # Step 4: Write to cache
    await cache.set_forecast(best.lat, best.lon, days, data_json)

    # Return as JSON string for LLM consumption
    return data_json
