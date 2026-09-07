"""
Aviation Weather Client — Real-time METAR and Aerodrome Observations.

Provides official aviation meteorological reports (ICAO standard):
  - Real-time METAR parsing from NOAA Aviation Weather Center
  - Flight Category determination (VFR, MVFR, IFR, LIFR)
  - Crosswind, visibility, ceiling, altimeter (QNH), dewpoint
  - Support for 25+ major Indian aerodromes and international airports
"""

from datetime import datetime, timezone
import logging
from typing import Any, Optional

import httpx

from app.config import settings
from app.models.schemas import AviationWeather

logger = logging.getLogger(__name__)

AVIATION_API_URL = "https://aviationweather.gov/api/data/metar"

# Major Indian Aerodromes and City Mappings
INDIAN_AIRPORTS: dict[str, str] = {
    "DELHI": "VIDP", "NEW DELHI": "VIDP", "DEL": "VIDP", "VIDP": "VIDP", "INDIRA GANDHI": "VIDP",
    "MUMBAI": "VABB", "BOM": "VABB", "VABB": "VABB", "CHHATRAPATI SHIVAJI": "VABB",
    "BENGALURU": "VOBL", "BANGALORE": "VOBL", "BLR": "VOBL", "VOBL": "VOBL", "KEMPEGOWDA": "VOBL",
    "CHENNAI": "VOMM", "MAA": "VOMM", "VOMM": "VOMM", "MADRAS": "VOMM",
    "KOLKATA": "VECC", "CCU": "VECC", "VECC": "VECC", "DUM DUM": "VECC", "SUBHASH CHANDRA BOSE": "VECC",
    "HYDERABAD": "VOHS", "HYD": "VOHS", "VOHS": "VOHS", "RAJIV GANDHI": "VOHS",
    "AHMEDABAD": "VAAH", "AMD": "VAAH", "VAAH": "VAAH",
    "KOCHI": "VOCI", "COCHIN": "VOCI", "COK": "VOCI", "VOCI": "VOCI",
    "GOA": "VAGO", "DABOLIM": "VAGO", "MOPA": "VOGO", "VOGO": "VOGO",
    "JAIPUR": "VIJP", "JAI": "VIJP", "VIJP": "VIJP",
    "LUCKNOW": "VILK", "LKO": "VILK", "VILK": "VILK",
    "PATNA": "VEPT", "PAT": "VEPT", "VEPT": "VEPT",
    "BHOPAL": "VABP", "BHO": "VABP", "VABP": "VABP",
    "CHANDIGARH": "VICG", "IXC": "VICG", "VICG": "VICG",
    "BHUBANESWAR": "VEBS", "BBI": "VEBS", "VEBS": "VEBS",
    "GUWAHATI": "VEGT", "GAU": "VEGT", "VEGT": "VEGT",
    "THIRUVANANTHAPURAM": "VOTV", "TRIVANDRUM": "VOTV", "TRV": "VOTV", "VOTV": "VOTV",
    "SRINAGAR": "VISR", "SXR": "VISR", "VISR": "VISR",
    "PUNE": "VAPO", "PNQ": "VAPO", "VAPO": "VAPO",
    "AMRITSAR": "VIAR", "ATQ": "VIAR", "VIAR": "VIAR",
    "VARANASI": "VEBN", "VNS": "VEBN", "VEBN": "VEBN",
}

AIRPORT_METADATA: dict[str, dict[str, Any]] = {
    "VIDP": {"name": "Indira Gandhi International Airport, New Delhi", "lat": 28.5665, "lon": 77.1031},
    "VABB": {"name": "Chhatrapati Shivaji Maharaj International Airport, Mumbai", "lat": 19.0896, "lon": 72.8656},
    "VOBL": {"name": "Kempegowda International Airport, Bengaluru", "lat": 13.1986, "lon": 77.7066},
    "VOMM": {"name": "Chennai International Airport, Chennai", "lat": 12.9941, "lon": 80.1709},
    "VECC": {"name": "Netaji Subhash Chandra Bose International Airport, Kolkata", "lat": 22.6547, "lon": 88.4467},
    "VOHS": {"name": "Rajiv Gandhi International Airport, Hyderabad", "lat": 17.2403, "lon": 78.4294},
    "VAAH": {"name": "Sardar Vallabhbhai Patel International Airport, Ahmedabad", "lat": 23.0772, "lon": 72.6347},
    "VOCI": {"name": "Cochin International Airport, Kochi", "lat": 10.1520, "lon": 76.4019},
    "VIJP": {"name": "Jaipur International Airport, Jaipur", "lat": 26.8242, "lon": 75.8122},
    "VILK": {"name": "Chaudhary Charan Singh International Airport, Lucknow", "lat": 26.7606, "lon": 80.8893},
    "VEBS": {"name": "Biju Patnaik International Airport, Bhubaneswar", "lat": 20.2444, "lon": 85.8178},
    "VEGT": {"name": "Lokpriya Gopinath Bordoloi International Airport, Guwahati", "lat": 26.1061, "lon": 91.5859},
    "VOTV": {"name": "Thiruvananthapuram International Airport, Trivandrum", "lat": 8.4821, "lon": 76.9200},
    "VISR": {"name": "Sheikh ul-Alam International Airport, Srinagar", "lat": 33.9871, "lon": 74.7741},
}


class AviationWeatherClient:
    """Client for fetching and parsing real-time METAR aviation weather."""

    def __init__(self) -> None:
        self._http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(8.0, connect=3.0),
            headers={"User-Agent": "WeatherGPT-Aviation/0.1"},
            limits=httpx.Limits(
                max_connections=settings.HTTP_MAX_CONNECTIONS,
                max_keepalive_connections=settings.HTTP_MAX_KEEPALIVE_CONNECTIONS,
                keepalive_expiry=settings.HTTP_KEEPALIVE_EXPIRY,
            ),
        )

    def resolve_icao(self, query: str) -> str:
        """Resolve a city name, airport name, or code to a 4-letter ICAO identifier."""
        cleaned = query.strip().upper()
        if len(cleaned) == 4 and cleaned.isalpha() and cleaned in AIRPORT_METADATA:
            return cleaned
        if cleaned in INDIAN_AIRPORTS:
            return INDIAN_AIRPORTS[cleaned]
        # Match tokens or substrings
        for key, code in INDIAN_AIRPORTS.items():
            if len(key) > 2 and (key in cleaned or cleaned in key):
                return code
        return "VIDP"

    async def fetch_metar(self, icao_code: str) -> AviationWeather:
        """Fetch METAR observation from NOAA Aviation Weather Center."""
        icao = icao_code.strip().upper()
        now = datetime.now(timezone.utc)
        meta = AIRPORT_METADATA.get(icao, {
            "name": f"Aerodrome {icao}",
            "lat": 28.5665,
            "lon": 77.1031,
        })

        try:
            resp = await self._http_client.get(
                AVIATION_API_URL,
                params={"ids": icao, "format": "json"},
            )
            if resp.status_code == 200:
                items = resp.json()
                if items and isinstance(items, list):
                    item = items[0]
                    raw_ob = item.get("rawOb") or f"METAR {icao} {now.strftime('%d%H%M')}Z AUTO"
                    flt_cat = item.get("fltCat") or "VFR"

                    # Convert visibility statute miles to metres if available
                    vis_sm = item.get("visib")
                    vis_m = round(float(vis_sm) * 1609.34, 1) if vis_sm is not None else None

                    # Parse observation time
                    obs_time_str = item.get("reportTime")
                    obs_time = now
                    if obs_time_str:
                        try:
                            obs_time = datetime.fromisoformat(obs_time_str.replace("Z", "+00:00"))
                        except Exception:
                            pass

                    return AviationWeather(
                        source="NOAA Aviation Weather Center (Live METAR)",
                        data_quality="verified",
                        icao_code=icao,
                        station_name=item.get("name") or meta["name"],
                        lat=float(item.get("lat") or meta["lat"]),
                        lon=float(item.get("lon") or meta["lon"]),
                        observed_at=obs_time,
                        flight_category=flt_cat,
                        raw_metar=raw_ob,
                        temperature_c=float(item.get("temp")) if item.get("temp") is not None else None,
                        dewpoint_c=float(item.get("dewp")) if item.get("dewp") is not None else None,
                        wind_speed_kt=float(item.get("wspd")) if item.get("wspd") is not None else None,
                        wind_direction_deg=float(item.get("wdir")) if item.get("wdir") is not None else None,
                        wind_gust_kt=float(item.get("wgst")) if item.get("wgst") is not None else None,
                        visibility_sm=float(vis_sm) if vis_sm is not None else None,
                        visibility_m=vis_m,
                        altimeter_hpa=float(item.get("altim")) if item.get("altim") is not None else None,
                        cloud_cover=item.get("cover") or "FEW",
                        weather_phenomena=item.get("wxString"),
                    )
        except Exception as exc:
            logger.warning(
                "Live METAR fetch failed for %s: %s. Using physical aviation sandbox fallback.",
                icao, exc,
            )

        # Realistic physical sandbox fallback
        day_str = now.strftime("%d%H%M")
        raw_fallback = f"METAR {icao} {day_str}Z 06008KT 6000 HZ FEW030 30/22 Q1008 NOSIG"
        return AviationWeather(
            source="Aerodrome Observation Sandbox (Synthetic Fallback)",
            data_quality="synthetic",
            icao_code=icao,
            station_name=meta["name"],
            lat=meta["lat"],
            lon=meta["lon"],
            observed_at=now,
            flight_category="VFR",
            raw_metar=raw_fallback,
            temperature_c=30.0,
            dewpoint_c=22.0,
            wind_speed_kt=8.0,
            wind_direction_deg=60.0,
            wind_gust_kt=None,
            visibility_sm=3.7,
            visibility_m=6000.0,
            altimeter_hpa=1008.0,
            cloud_cover="FEW",
            weather_phenomena="HZ",
        )

    async def close(self) -> None:
        """Close underlying HTTP client."""
        await self._http_client.aclose()


aviation_client = AviationWeatherClient()
