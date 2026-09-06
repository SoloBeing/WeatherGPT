"""
get_alerts(location, min_severity) — Active weather and disaster alerts.

Queries NDMA SACHET CAP alerts and IMD district warnings for a named location,
district, or state with spatial and keyword matching.
"""

import json
import logging
from typing import Optional

from app.pipelines.sachet_poller import sachet_poller
from app.models.schemas import AlertListResponse
from app.tools.location_resolver import resolve_location

logger = logging.getLogger(__name__)


async def get_alerts(location: str, min_severity: Optional[str] = None) -> str:
    """Get active disaster and weather alerts for a location or region.

    This is the tool function called by the LLM orchestrator.

    Flow:
        1. Resolve location name → lat/lon, state, district
        2. Query SachetPoller for active CAP alerts matching point/region
        3. Filter by severity if specified ("Minor", "Moderate", "Severe", "Extreme")
        4. Return structured JSON with active alert details

    Args:
        location: City, district, or state name (e.g. "Odisha", "Mumbai", "Jaipur", "Kerala").
        min_severity: Optional minimum severity level ("Moderate", "Severe", "Extreme").

    Returns:
        JSON string with AlertListResponse.
    """
    # Step 1: Resolve location name to coordinates & administrative boundaries
    lat: Optional[float] = None
    lon: Optional[float] = None
    state: Optional[str] = None
    district: Optional[str] = None
    location_display = location

    try:
        matches = await resolve_location(location)
        if matches:
            best = matches[0]
            lat = best.lat
            lon = best.lon
            state = best.admin1
            district = best.admin2
            location_display = best.name
            if best.admin1:
                location_display += f", {best.admin1}"
            if best.country:
                location_display += f", {best.country}"
    except Exception as e:
        logger.warning("Location resolution warning for '%s': %s (falling back to direct query)", location, e)

    # Step 2: Query active alerts
    alerts = sachet_poller.get_alerts_for_location(
        location_name=location,
        lat=lat,
        lon=lon,
        state=state,
        district=district,
        min_severity=min_severity,
    )

    logger.info(
        "Alert lookup for '%s' (lat=%s, lon=%s): %d active alerts found",
        location_display, lat, lon, len(alerts),
    )

    # Step 3: Format output
    result = AlertListResponse(
        location_name=location_display,
        lat=lat,
        lon=lon,
        count=len(alerts),
        alerts=alerts,
    )

    return result.model_dump_json(exclude_none=True)
