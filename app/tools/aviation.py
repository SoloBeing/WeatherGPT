"""
get_aviation_weather(airport) — Aerodrome METAR and flight weather.

Fetches official METAR reports, flight categories (VFR/IFR), runway visibility,
wind speed/direction, and cloud ceiling for Indian and international aerodromes.
"""

import logging

from app.data_sources.aviation import aviation_client

logger = logging.getLogger(__name__)


async def get_aviation_weather(airport: str) -> str:
    """Get official METAR aviation weather and flight category for an airport.

    This tool is called when the user asks about airport weather, flight conditions,
    METAR reports, runway visibility, or crosswinds at a specific aerodrome.

    Args:
        airport: Airport name, 4-letter ICAO code, 3-letter IATA code, or city
                 (e.g. "VIDP", "Delhi Airport", "VABB", "Mumbai", "BLR", "VOBL", "Goa").

    Returns:
        JSON string containing AviationWeather report.
    """
    icao = aviation_client.resolve_icao(airport)
    logger.info("Fetching aviation weather for '%s' -> ICAO '%s'", airport, icao)
    metar_data = await aviation_client.fetch_metar(icao)
    return metar_data.model_dump_json(exclude_none=True)
