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
from typing import Any, Optional

import httpx

from app.config import settings
from app.core.resilience import classify_http_error, retry_async
from app.models.schemas import LocationMatch

logger = logging.getLogger(__name__)

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

_geocoder_client: Optional[httpx.AsyncClient] = None
_client_cls: Any = None
_LOCATION_CACHE: dict[str, list[LocationMatch]] = {}
_MAX_CACHE_ENTRIES = 1024


def get_geocoder_client() -> httpx.AsyncClient:
    """Get or create the persistent, connection-pooled geocoder HTTP client."""
    global _geocoder_client, _client_cls
    current_cls = httpx.AsyncClient
    if _geocoder_client is None or _geocoder_client.is_closed or _client_cls != current_cls:
        limits = httpx.Limits(
            max_connections=settings.HTTP_MAX_CONNECTIONS,
            max_keepalive_connections=settings.HTTP_MAX_KEEPALIVE_CONNECTIONS,
            keepalive_expiry=settings.HTTP_KEEPALIVE_EXPIRY,
        )
        timeout = httpx.Timeout(settings.HTTP_TIMEOUT, connect=5.0)
        _geocoder_client = httpx.AsyncClient(
            timeout=timeout,
            limits=limits,
            headers={"User-Agent": "WeatherGPT/0.1"},
        )
        _client_cls = current_cls
    return _geocoder_client


async def close_geocoder() -> None:
    """Close the geocoder HTTP client and reset state."""
    global _geocoder_client, _client_cls
    if _geocoder_client is not None:
        await _geocoder_client.aclose()
        _geocoder_client = None
        _client_cls = None


def clear_location_cache() -> None:
    """Clear in-memory location resolution cache."""
    _LOCATION_CACHE.clear()

# Common Indian States, Union Territories, and Major Cities gazetteer
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
    # Top Indian Metropolitan Hubs & Key Cities
    "mumbai": (19.0760, 72.8777, "Mumbai"),
    "bombay": (19.0760, 72.8777, "Mumbai"),
    "bengaluru": (12.9716, 77.5946, "Bengaluru"),
    "bangalore": (12.9716, 77.5946, "Bengaluru"),
    "kolkata": (22.5726, 88.3639, "Kolkata"),
    "calcutta": (22.5726, 88.3639, "Kolkata"),
    "chennai": (13.0827, 80.2707, "Chennai"),
    "madras": (13.0827, 80.2707, "Chennai"),
    "hyderabad": (17.3850, 78.4867, "Hyderabad"),
    "ahmedabad": (23.0225, 72.5714, "Ahmedabad"),
    "pune": (18.5204, 73.8567, "Pune"),
    "jaipur": (26.9124, 75.7873, "Jaipur"),
    "lucknow": (26.8467, 80.9462, "Lucknow"),
    "patna": (25.5941, 85.1376, "Patna"),
    "bhopal": (23.2599, 77.4126, "Bhopal"),
    "bhubaneswar": (20.2961, 85.8245, "Bhubaneswar"),
    "thiruvananthapuram": (8.5241, 76.9366, "Thiruvananthapuram"),
    "trivandrum": (8.5241, 76.9366, "Thiruvananthapuram"),
    "guwahati": (26.1445, 91.7362, "Guwahati"),
    "srinagar": (34.0837, 74.7973, "Srinagar"),
    "shimla": (31.1048, 77.1734, "Shimla"),
    "dehradun": (30.3165, 78.0322, "Dehradun"),
    "ranchi": (23.3441, 85.3096, "Ranchi"),
    "raipur": (21.2514, 81.6296, "Raipur"),
    "panaji": (15.4909, 73.8278, "Panaji"),
    "surat": (21.1702, 72.8311, "Surat"),
    "kanpur": (26.4499, 80.3319, "Kanpur"),
    "nagpur": (21.1458, 79.0882, "Nagpur"),
    "indore": (22.7196, 75.8577, "Indore"),
    "varanasi": (25.3176, 82.9739, "Varanasi"),
    "banaras": (25.3176, 82.9739, "Varanasi"),
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
    cache_key = f"{clean_name}:{count}:{country_code or ''}"

    if cache_key in _LOCATION_CACHE:
        logger.debug("Location cache HIT for '%s'", name)
        return _LOCATION_CACHE[cache_key]

    # Check Indian states gazetteer table first
    if clean_name in INDIAN_STATES_GAZETTEER:
        lat, lon, state_name = INDIAN_STATES_GAZETTEER[clean_name]
        logger.info("Gazetteer hit for Indian state: %s (%.2f, %.2f)", state_name, lat, lon)
        res = [
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
        _LOCATION_CACHE[cache_key] = res
        return res
    params: dict = {
        "name": name,
        "count": count,
        "language": "en",
        "format": "json",
    }
    if country_code:
        params["country_code"] = country_code

    async def _fetch_geocoding() -> dict:
        client = get_geocoder_client()
        resp = await client.get(GEOCODING_URL, params=params)
        resp.raise_for_status()
        return resp.json()

    try:
        data = await retry_async(
            _fetch_geocoding,
            max_retries=2,
            base_delay=0.3,
            max_delay=2.0,
            operation_name=f"Geocoding '{name}'",
        )
        results = data.get("results", [])
    except Exception as exc:
        logger.warning(
            "Geocoding service unavailable for '%s': %s. Attempting offline fallback.",
            name,
            classify_http_error(exc),
        )
        # Offline substring fallback against built-in gazetteer
        for key, (lat, lon, place_name) in INDIAN_STATES_GAZETTEER.items():
            if key in clean_name or clean_name in key:
                logger.info("Fallback gazetteer hit for '%s' -> %s", name, place_name)
                return [
                    LocationMatch(
                        name=place_name,
                        lat=lat,
                        lon=lon,
                        country="India",
                        country_code="IN",
                        admin1=place_name,
                        confidence=0.8,
                    )
                ]
        return []
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

    if matches:
        if len(_LOCATION_CACHE) >= _MAX_CACHE_ENTRIES:
            _LOCATION_CACHE.clear()
        _LOCATION_CACHE[cache_key] = matches

    return matches
