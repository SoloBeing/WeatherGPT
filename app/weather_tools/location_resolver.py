"""
Location Resolver — Disambiguate Indian place names.

From the spec:
  "Indian place names are ambiguous and voice input mangles them.
   Build a gazetteer table (village/town/district, ~600k rows from
   LGD or GeoNames) with pg_trgm fuzzy matching, and resolve BEFORE
   the LLM sees the query."

Ask a disambiguating question when confidence is low.

For Session 02 we use the Open-Meteo Geocoding API as a fast, no-key
geocoder. The pg_trgm gazetteer is planned for Session 03.
"""

import logging
from typing import Optional

import httpx

from app.schemas_and_models.schemas import LocationMatch

logger = logging.getLogger(__name__)

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"


async def resolve_location(
    name: str,
    count: int = 5,
    country_code: Optional[str] = None,
) -> list[LocationMatch]:
    """Resolve a location name to geographic coordinates.

    Uses the Open-Meteo Geocoding API (free, no key).

    Args:
        name: City, town, or place name (e.g. "Delhi", "Jaipur").
        count: Max number of results to return.
        country_code: Optional ISO-3166 country code to prioritise (e.g. "IN").

    Returns:
        List of LocationMatch objects, ranked by relevance.
        Empty list if no matches found.
    """
    params: dict = {
        "name": name,
        "count": count,
        "language": "en",
        "format": "json",
    }
    if country_code:
        params["country_code"] = country_code

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(GEOCODING_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    results = data.get("results", [])
    if not results:
        logger.warning("Geocoding returned no results for: %s", name)
        return []

    matches = [
        LocationMatch(
            name=r["name"],
            lat=r["latitude"],
            lon=r["longitude"],
            country=r.get("country"),
            country_code=r.get("country_code"),
            admin1=r.get("admin1"),
            admin2=r.get("admin2"),
            elevation=r.get("elevation"),
            timezone=r.get("timezone"),
            population=r.get("population"),
            # Crude confidence: first result is best, decays by rank
            confidence=round(max(0.1, 1.0 - i * 0.15), 2),
        )
        for i, r in enumerate(results)
    ]

    # Prefer Indian results when no country filter was specified
    if not country_code:
        indian = [m for m in matches if m.country_code == "IN"]
        non_indian = [m for m in matches if m.country_code != "IN"]
        if indian:
            matches = indian + non_indian

    logger.info(
        "Resolved '%s' → %d matches (best: %s, %s)",
        name, len(matches), matches[0].name, matches[0].country,
    )
    return matches
