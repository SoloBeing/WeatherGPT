"""
Open-Meteo Client — Free, no-key, REST API.

Provides: GFS/ECMWF/ICON blended, hourly, 16-day forecast.
Also: Open-Meteo Flood API (GloFAS river discharge).
This is the always-available fallback behind the same internal interface.
"""

import logging
from datetime import date, datetime, timezone

import httpx

from app.config import settings
from app.data_sources.base import BaseDataSource
from app.schemas_and_models.schemas import (
    DailyForecast,
    ForecastPoint,
    ForecastTimeline,
    HourlyForecast,
)

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

# Daily forecast variables to request from Open-Meteo
_DAILY_PARAMS: list[str] = [
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_min",
    "apparent_temperature_max",
    "apparent_temperature_min",
    "sunrise",
    "sunset",
    "uv_index_max",
    "precipitation_sum",
    "rain_sum",
    "snowfall_sum",
    "precipitation_probability_max",
    "wind_speed_10m_max",
    "wind_gusts_10m_max",
    "wind_direction_10m_dominant",
]

# Hourly forecast variables (when detailed slice is requested)
_HOURLY_PARAMS: list[str] = [
    "temperature_2m",
    "relative_humidity_2m",
    "apparent_temperature",
    "precipitation_probability",
    "precipitation",
    "weather_code",
    "wind_speed_10m",
    "is_day",
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

    async def fetch_forecast(
        self,
        lat: float,
        lon: float,
        days: int = 7,
        include_hourly: bool = False,
    ) -> ForecastTimeline:
        """Fetch multi-day weather forecast from Open-Meteo.

        Args:
            lat: Latitude (WGS84)
            lon: Longitude (WGS84)
            days: Forecast horizon in days (1 to 16, default 7)
            include_hourly: Whether to include hourly breakdown

        Returns:
            ForecastTimeline containing daily and optionally hourly forecast items.
        """
        forecast_days = max(1, min(days, 16))
        params: dict = {
            "latitude": lat,
            "longitude": lon,
            "daily": ",".join(_DAILY_PARAMS),
            "timezone": "auto",
            "wind_speed_unit": "kmh",
            "forecast_days": forecast_days,
        }

        if include_hourly:
            params["hourly"] = ",".join(_HOURLY_PARAMS)

        resp = await self._client.get("/forecast", params=params)
        resp.raise_for_status()
        data = resp.json()

        daily_data = data.get("daily", {})
        times = daily_data.get("time", [])

        daily_items: list[DailyForecast] = []
        for i, t_str in enumerate(times):
            try:
                f_date = date.fromisoformat(t_str)
            except ValueError:
                continue

            w_code = daily_data.get("weather_code", [None])[i] if i < len(daily_data.get("weather_code", [])) else None

            # Helper for safe indexing
            def _get_val(key: str, idx: int):
                vals = daily_data.get(key, [])
                return vals[idx] if idx < len(vals) else None

            # Parse sunrise / sunset
            sunrise_str = _get_val("sunrise", i)
            sunset_str = _get_val("sunset", i)
            sunrise_dt = None
            sunset_dt = None
            if sunrise_str:
                try:
                    sunrise_dt = datetime.fromisoformat(sunrise_str)
                except ValueError:
                    pass
            if sunset_str:
                try:
                    sunset_dt = datetime.fromisoformat(sunset_str)
                except ValueError:
                    pass

            daily_items.append(
                DailyForecast(
                    date=f_date,
                    temp_max_c=_get_val("temperature_2m_max", i),
                    temp_min_c=_get_val("temperature_2m_min", i),
                    feels_like_max_c=_get_val("apparent_temperature_max", i),
                    feels_like_min_c=_get_val("apparent_temperature_min", i),
                    precipitation_sum_mm=_get_val("precipitation_sum", i),
                    rain_sum_mm=_get_val("rain_sum", i),
                    snowfall_sum_cm=_get_val("snowfall_sum", i),
                    precipitation_probability_max_pct=_get_val("precipitation_probability_max", i),
                    wind_speed_max_kmh=_get_val("wind_speed_10m_max", i),
                    wind_gusts_max_kmh=_get_val("wind_gusts_10m_max", i),
                    wind_direction_dominant_deg=_get_val("wind_direction_10m_dominant", i),
                    uv_index_max=_get_val("uv_index_max", i),
                    weather_code=w_code,
                    weather_description=WMO_WEATHER_CODES.get(w_code, "Unknown") if w_code is not None else None,
                    sunrise=sunrise_dt,
                    sunset=sunset_dt,
                )
            )

        hourly_items: list[HourlyForecast] | None = None
        if include_hourly and "hourly" in data:
            hourly_data = data["hourly"]
            h_times = hourly_data.get("time", [])
            hourly_items = []
            for j, ht_str in enumerate(h_times):
                try:
                    h_dt = datetime.fromisoformat(ht_str)
                except ValueError:
                    continue

                def _get_h_val(key: str, idx: int):
                    vals = hourly_data.get(key, [])
                    return vals[idx] if idx < len(vals) else None

                hw_code = _get_h_val("weather_code", j)
                hourly_items.append(
                    HourlyForecast(
                        valid_at=h_dt,
                        temperature_c=_get_h_val("temperature_2m", j),
                        feels_like_c=_get_h_val("apparent_temperature", j),
                        humidity_pct=_get_h_val("relative_humidity_2m", j),
                        precipitation_mm=_get_h_val("precipitation", j),
                        precipitation_probability_pct=_get_h_val("precipitation_probability", j),
                        wind_speed_kmh=_get_h_val("wind_speed_10m", j),
                        weather_code=hw_code,
                        weather_description=WMO_WEATHER_CODES.get(hw_code, "Unknown") if hw_code is not None else None,
                        is_day=bool(_get_h_val("is_day", j)) if _get_h_val("is_day", j) is not None else None,
                    )
                )

        logger.debug(
            "Open-Meteo forecast: lat=%.4f lon=%.4f days=%d items=%d",
            lat, lon, forecast_days, len(daily_items),
        )

        return ForecastTimeline(
            source=self.source_name,
            issued_at=datetime.now(timezone.utc),
            lat=data["latitude"],
            lon=data["longitude"],
            timezone=data.get("timezone"),
            daily=daily_items,
            hourly=hourly_items,
        )

    async def close(self) -> None:
        """Close the underlying httpx client."""
        await self._client.aclose()
