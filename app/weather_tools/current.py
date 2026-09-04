"""
get_current(lat, lon) — Current weather conditions.

Returns: temperature, humidity, wind speed/dir, pressure, cloud cover,
precipitation, weather code. Sources: Open-Meteo → IMD fallback.
"""

import json
import logging

from app.database.redis_cache import cache
from app.data_sources.openmeteo import OpenMeteoClient
from app.weather_tools.location_resolver import resolve_location

logger = logging.getLogger(__name__)


async def get_current_weather(location: str) -> str:
    """Get current weather conditions for a named location.

    This is the tool function that the LLM calls via tool-calling.

    Flow:
        1. Resolve location name → lat/lon (Open-Meteo geocoding)
        2. Check Redis cache first (TTL 1h)
        3. If cache miss, fetch current weather → ForecastPoint (Open-Meteo)
        4. Populate cache and return JSON string for LLM consumption

    Args:
        location: City or place name (e.g. "Delhi", "Mumbai", "Jaipur").

    Returns:
        JSON string with weather data or error message.
    """
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
    cached_data = await cache.get_current_weather(best.lat, best.lon)
    if cached_data:
        logger.info("Cache HIT for current weather at %s (%.4f, %.4f)", location_display, best.lat, best.lon)
        return cached_data

    logger.debug("Cache MISS for current weather at %s (%.4f, %.4f)", location_display, best.lat, best.lon)

    # Step 3: Fetch current weather (GFS NWP Zarr primary for India, Open-Meteo fallback)
    point = None
    from app.data_sources.gfs import gfs_client

    if gfs_client.has_data_for(best.lat, best.lon):
        try:
            logger.info("Extracting current weather from NOAA GFS 0.25° Zarr store for %s", location_display)
            point = await gfs_client.fetch_current(best.lat, best.lon)
            point.location_name = location_display
        except Exception as e:
            logger.warning("GFS Zarr extraction failed for %s (%s), falling back to Open-Meteo", location_display, e)

    if point is None:
        client = OpenMeteoClient()
        try:
            point = await client.fetch_current(best.lat, best.lon)
            point.location_name = location_display
        except Exception as e:
            logger.error("Weather fetch failed for %s (%.4f, %.4f): %s", location, best.lat, best.lon, e)
            return json.dumps({"error": f"Weather data unavailable for {location}. {e}"})
        finally:
            await client.close()

    logger.info(
        "Current weather for %s: %.1f°C, %s",
        location_display,
        point.temperature_c or 0,
        point.weather_description,
    )

    data_json = point.model_dump_json(exclude_none=True)

    # Step 4: Write to cache
    await cache.set_current_weather(best.lat, best.lon, data_json)

    # Return as JSON string for LLM consumption
    return data_json
