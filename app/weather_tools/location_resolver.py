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

# Common Indian States and Union Territories gazetteer
INDIAN_STATES_GAZETTEER: dict[str, tuple[float, float, str]] = {
    "andaman and nicobar": (11.74, 92.65, "Andaman and Nicobar Islands"),
    "andhra pradesh": (15.91, 79.74, "Andhra Pradesh"),
    "arunachal pradesh": (28.21, 94.72, "Arunachal Pradesh"),
    "assam": (26.20, 92.93, "Assam"),
    "bihar": (25.09, 85.31, "Bihar"),
    "chandigarh": (30.73, 76.77, "Chandigarh"),
    "chhattisgarh": (21.27, 81.86, "Chhattisgarh"),
    "delhi": (28.61, 77.20, "Delhi"),
    "goa": (15.29, 74.12, "Goa"),
    "gujarat": (22.25, 71.19, "Gujarat"),
    "haryana": (29.05, 76.08, "Haryana"),
    "himachal pradesh": (31.10, 77.17, "Himachal Pradesh"),
    "jammu and kashmir": (33.77, 76.57, "Jammu and Kashmir"),
    "jharkhand": (23.61, 85.27, "Jharkhand"),
    "karnataka": (15.31, 75.71, "Karnataka"),
    "kerala": (10.85, 76.27, "Kerala"),
    "ladakh": (34.15, 77.57, "Ladakh"),
    "lakshadweep": (10.56, 72.64, "Lakshadweep"),
    "madhya pradesh": (22.97, 78.65, "Madhya Pradesh"),
    "maharashtra": (19.75, 75.71, "Maharashtra"),
    "manipur": (24.66, 93.90, "Manipur"),
    "meghalaya": (25.46, 91.36, "Meghalaya"),
    "mizoram": (23.16, 92.93, "Mizoram"),
    "nagaland": (26.15, 94.56, "Nagaland"),
    "odisha": (20.95, 85.09, "Odisha"),
    "orissa": (20.95, 85.09, "Odisha"),
    "puducherry": (11.94, 79.80, "Puducherry"),
    "punjab": (31.14, 75.34, "Punjab"),
    "rajasthan": (27.02, 74.21, "Rajasthan"),
    "sikkim": (27.53, 88.51, "Sikkim"),
    "tamil nadu": (11.12, 78.65, "Tamil Nadu"),
    "telangana": (18.11, 79.01, "Telangana"),
    "tripura": (23.94, 91.98, "Tripura"),
    "uttar pradesh": (26.84, 80.94, "Uttar Pradesh"),
    "uttarakhand": (30.06, 79.01, "Uttarakhand"),
    "west bengal": (22.98, 87.85, "West Bengal"),
}


async def resolve_location(
    name: str,
    count: int = 5,
    country_code: Optional[str] = None,
) -> list[LocationMatch]:
    """Resolve a location name to geographic coordinates.

    Uses the Open-Meteo Geocoding API (free, no key) with Indian State Gazetteer.

    Args:
        name: City, town, or place name (e.g. "Delhi", "Jaipur", "Odisha").
        count: Max number of results to return.
        country_code: Optional ISO-3166 country code to prioritise (e.g. "IN").

    Returns:
        List of LocationMatch objects, ranked by relevance.
        Empty list if no matches found.
    """
    clean_name = name.strip().lower()

    # Check Indian states gazetteer table first
    if clean_name in INDIAN_STATES_GAZETTEER:
        lat, lon, state_name = INDIAN_STATES_GAZETTEER[clean_name]
        logger.info("Gazetteer hit for Indian state: %s (%.2f, %.2f)", state_name, lat, lon)
        return [
            LocationMatch(
                name=state_name,
                lat=lat,
                lon=lon,
                country="India",
                country_code="IN",
                admin1=state_name,
                confidence=1.0,
            )
        ]
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
