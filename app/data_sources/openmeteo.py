"""
Open-Meteo Client — Free, no-key, REST API.

Provides: GFS/ECMWF/ICON blended, hourly, 16-day forecast.
Also: Open-Meteo Flood API (GloFAS river discharge).
This is the always-available fallback behind the same internal interface.
"""

import logging
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.data_sources.base import BaseDataSource
from app.schemas_and_models.schemas import ForecastPoint

logger = logging.getLogger(__name__)

# WMO Weather Interpretation Codes (WW)
# https://open-meteo.com/en/docs#weathervariables
WMO_WEATHER_CODES: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snowfall",
    73: "Moderate snowfall",
    75: "Heavy snowfall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}

# Current-weather variables to request from Open-Meteo
_CURRENT_PARAMS: list[str] = [
    "temperature_2m",
    "relative_humidity_2m",
    "apparent_temperature",
    "is_day",
    "precipitation",
    "rain",
    "snowfall",
    "weather_code",
    "cloud_cover",
    "pressure_msl",
    "surface_pressure",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
]


class OpenMeteoClient(BaseDataSource):
    """Async client for the Open-Meteo forecast API.

    No API key required.  Returns a ForecastPoint with current conditions.
    """

    source_name: str = "open-meteo"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.OPENMETEO_BASE_URL,
            timeout=10.0,
            headers={"User-Agent": "WeatherGPT/0.1"},
        )

    async def fetch_current(self, lat: float, lon: float) -> ForecastPoint:
        """Fetch current weather from Open-Meteo /forecast endpoint.

        Args:
            lat: Latitude (WGS84)
            lon: Longitude (WGS84)

        Returns:
            ForecastPoint with all available current-weather fields.

        Raises:
            httpx.HTTPStatusError: If the API returns a non-2xx response.
        """
        resp = await self._client.get(
            "/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": ",".join(_CURRENT_PARAMS),
                "timezone": "auto",
                "wind_speed_unit": "kmh",
            },
        )
        resp.raise_for_status()
        data = resp.json()

        current = data["current"]
        weather_code = current.get("weather_code")

        # Parse the time string — Open-Meteo returns ISO-8601 without tz info
        # but the timezone is in the top-level response
        valid_time_str = current["time"]
        try:
            valid_at = datetime.fromisoformat(valid_time_str)
        except ValueError:
            valid_at = datetime.now(timezone.utc)

        logger.debug(
            "Open-Meteo current: lat=%.4f lon=%.4f temp=%.1f°C code=%s",
            lat, lon, current.get("temperature_2m", 0), weather_code,
        )

        return ForecastPoint(
            source=self.source_name,
            issued_at=datetime.now(timezone.utc),
            valid_at=valid_at,
            lat=data["latitude"],
            lon=data["longitude"],
            temperature_c=current.get("temperature_2m"),
            feels_like_c=current.get("apparent_temperature"),
            humidity_pct=current.get("relative_humidity_2m"),
            wind_speed_kmh=current.get("wind_speed_10m"),
            wind_direction_deg=current.get("wind_direction_10m"),
            wind_gusts_kmh=current.get("wind_gusts_10m"),
            pressure_hpa=current.get("pressure_msl"),
            surface_pressure_hpa=current.get("surface_pressure"),
            cloud_cover_pct=current.get("cloud_cover"),
            precipitation_mm=current.get("precipitation"),
            rain_mm=current.get("rain"),
            snowfall_cm=current.get("snowfall"),
            weather_code=weather_code,
            weather_description=WMO_WEATHER_CODES.get(weather_code, "Unknown"),
            is_day=bool(current.get("is_day")),
        )

    async def close(self) -> None:
        """Close the underlying httpx client."""
        await self._client.aclose()
