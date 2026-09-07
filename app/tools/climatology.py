"""
get_climatology(location, variable, start_year, end_year) — Historical climate data.

Sources: ECMWF ERA5 (1940→present via Open-Meteo Archive), IMD Pune gridded normals.
Used for climate normals, seasonal anomalies, standard deviation, and decadal trends.
"""

import logging

from app.data_sources.era5 import era5_client
from app.tools.location_resolver import resolve_location

logger = logging.getLogger(__name__)


async def get_climatology(
    location: str,
    variable: str = "temperature",
    start_year: int = 1991,
    end_year: int = 2020,
) -> str:
    """Retrieve historical climatological normals, anomalies, and multi-decadal trends.

    Use this tool when the user asks about historical weather patterns, climate normals,
    past rainfall or temperature averages, climate change/warming trends, or long-term statistics
    for a city or region in India.

    Args:
        location: City, state, or district name (e.g. "Delhi", "Bengaluru", "Rajasthan", "Cherrapunji").
        variable: Meteorological variable to analyse ('temperature', 'precipitation', or 'all').
        start_year: Start year of baseline period (e.g. 1991 for standard WMO normal).
        end_year: End year of baseline period (e.g. 2020 for standard WMO normal).

    Returns:
        JSON string containing ClimatologyReport.
    """
    lat = 28.6139
    lon = 77.2090
    resolved_name = location

    try:
        matches = await resolve_location(location)
        if matches:
            lat = matches[0].lat
            lon = matches[0].lon
            resolved_name = matches[0].name
            if matches[0].admin1:
                resolved_name += f", {matches[0].admin1}"
    except Exception as exc:
        logger.warning("Climatology location resolution fallback for '%s': %s", location, exc)

    logger.info(
        "Computing historical climatology for '%s' (%s, %s) [%d-%d, var=%s]",
        resolved_name,
        lat,
        lon,
        start_year,
        end_year,
        variable,
    )

    report = await era5_client.fetch_climatology(
        lat=lat,
        lon=lon,
        location_name=resolved_name,
        variable=variable,
        start_year=start_year,
        end_year=end_year,
    )
    return report.model_dump_json()
