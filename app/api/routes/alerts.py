"""
Alerts Routes — Direct REST endpoints for active disaster warnings and alerts.

  - GET /alerts?location=... (active alerts matching location or coordinates)
  - GET /alerts/active (all currently tracked disaster alerts across India)
"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import AlertListResponse, AlertRecord
from app.pipelines.sachet_poller import sachet_poller
from app.tools.alerts_tool import get_alerts

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=dict)
async def get_alerts_endpoint(
    location: Optional[str] = Query(None, description="City, district, or state name (e.g. 'Chennai', 'Odisha')"),
    lat: Optional[float] = Query(None, ge=-90.0, le=90.0, description="Latitude coordinate"),
    lon: Optional[float] = Query(None, ge=-180.0, le=180.0, description="Longitude coordinate"),
    min_severity: Optional[str] = Query(None, description="Minimum severity: 'Moderate', 'Severe', 'Extreme'"),
) -> dict:
    """Retrieve active disaster and meteorological alerts for a specific area."""
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
        raw_json = await get_alerts(location=query_loc, min_severity=min_severity)
        data = json.loads(raw_json)
        return data
    except Exception as exc:
        logger.exception("Failed to query alerts for %s: %s", query_loc, exc)
        raise HTTPException(status_code=500, detail=f"Alerts service error: {exc}") from exc


@router.get("/active", response_model=list[AlertRecord])
async def list_active_alerts() -> list[AlertRecord]:
    """Retrieve all currently active NDMA SACHET and IMD disaster alerts nationwide."""
    try:
        return sachet_poller.get_all_active()
    except Exception as exc:
        logger.exception("Failed to fetch nationwide active alerts: %s", exc)
        raise HTTPException(status_code=500, detail=f"Alerts service error: {exc}") from exc

