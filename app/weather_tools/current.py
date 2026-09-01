"""
get_current(lat, lon) — Current weather conditions.

Returns: temperature, humidity, wind speed/dir, pressure, cloud cover,
precipitation, weather code. Sources: Open-Meteo → IMD fallback.
"""

import json
import logging

from app.data_sources.openmeteo import OpenMeteoClient
from app.weather_tools.location_resolver import resolve_location

logger = logging.getLogger(__name__)


async def get_current_weather(location: str) -> str:
    """Get current weather conditions for a named location.

    This is the tool function that the LLM calls via tool-calling.

    Flow:
        1. Resolve location name → lat/lon (Open-Meteo geocoding)
        2. Fetch current weather → ForecastPoint (Open-Meteo forecast)
        3. Return JSON string for LLM consumption

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

    # Step 2: Fetch current weather from Open-Meteo
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

    # Return as JSON string for LLM consumption
    return point.model_dump_json(exclude_none=True)
