"""
get_marine_weather(location, lat, lon) — Ocean state and coastal advisories.

Provides wave height, swell, currents, sea state conditions, and INCOIS
Potential Fishing Zone (PFZ) guidance for coastal districts and ports.
"""

import logging
from typing import Optional

from app.data_sources.incois import incois_client
from app.tools.location_resolver import resolve_location

logger = logging.getLogger(__name__)


async def get_marine_weather(
    location: str,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
) -> str:
    """Get marine weather, wave height, sea state, and PFZ advisory for coastal regions.

    This tool is called when the user asks about sea conditions, wave heights,
    swell, ocean currents, marine weather, or fishing / PFZ advisories.

    Args:
        location: Coastal town, port, or oceanic region (e.g. "Chennai", "Kochi", "Puri", "Goa", "Mumbai Offshore").
        lat: Optional latitude.
        lon: Optional longitude.

    Returns:
        JSON string containing MarinePoint details.
    """
    target_lat = lat
    target_lon = lon
    target_name = location

    if target_lat is None or target_lon is None:
        try:
            matches = await resolve_location(location)
            if matches:
                target_lat = matches[0].lat
                target_lon = matches[0].lon
                target_name = matches[0].name
                if matches[0].admin1:
                    target_name += f", {matches[0].admin1}"
        except Exception as exc:
            logger.warning("Marine location resolution error for '%s': %s", location, exc)

    # Fallback to default coastal coordinates (e.g. Mumbai coast 18.9, 72.8) if unresolved
    if target_lat is None or target_lon is None:
        target_lat = 18.9220
        target_lon = 72.8347
        target_name = f"{location} (Coastal Approximation)"

    logger.info("Fetching marine weather for '%s' (%s, %s)", target_name, target_lat, target_lon)
    marine_data = await incois_client.fetch_marine_weather(
        lat=target_lat,
        lon=target_lon,
        location_name=target_name,
    )
    return marine_data.model_dump_json(exclude_none=True)
