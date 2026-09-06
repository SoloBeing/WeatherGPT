"""
Pydantic Schemas — Request/response models and the ForecastPoint contract.

Core types:
  - ForecastPoint: the universal output format from all data sources
  - ChatRequest / ChatResponse: chat endpoint models
  - AlertRecord: parsed CAP alert with geometry
  - LocationMatch: gazetteer fuzzy match result
"""

from datetime import date as dt_date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class ForecastPoint(BaseModel):
    """Universal output format from all data sources.

    Every source — Open-Meteo, IMD, GFS, ECMWF, ERA5, WRF — normalises to
    this object. Swapping sources is a config change, and you can cite
    provenance in the answer ("per IMD, issued 08:30 IST").
    """

    source: str = Field(..., description="Data source identifier, e.g. 'open-meteo', 'imd'")
    issued_at: datetime = Field(..., description="When the source produced this data")
    valid_at: datetime = Field(..., description="What time the forecast/observation is for")
    lat: float
    lon: float
    location_name: Optional[str] = None

    # Core weather variables — all Optional since not every source provides everything
    temperature_c: Optional[float] = Field(None, description="Temperature in °C")
    feels_like_c: Optional[float] = Field(None, description="Apparent temperature in °C")
    humidity_pct: Optional[float] = Field(None, description="Relative humidity in %")
    wind_speed_kmh: Optional[float] = Field(None, description="Wind speed in km/h")
    wind_direction_deg: Optional[float] = Field(None, description="Wind direction in degrees")
    wind_gusts_kmh: Optional[float] = Field(None, description="Wind gusts in km/h")
    pressure_hpa: Optional[float] = Field(None, description="Mean sea level pressure in hPa")
    surface_pressure_hpa: Optional[float] = Field(None, description="Surface pressure in hPa")
    cloud_cover_pct: Optional[float] = Field(None, description="Cloud cover in %")
    precipitation_mm: Optional[float] = Field(None, description="Total precipitation in mm")
    rain_mm: Optional[float] = Field(None, description="Rain in mm")
    snowfall_cm: Optional[float] = Field(None, description="Snowfall in cm")
    visibility_m: Optional[float] = Field(None, description="Visibility in metres")
    uv_index: Optional[float] = Field(None, description="UV index")
    weather_code: Optional[int] = Field(None, description="WMO weather code")
    weather_description: Optional[str] = Field(None, description="Human-readable weather description")
    is_day: Optional[bool] = Field(None, description="True if daytime at the location")


class DailyForecast(BaseModel):
    """Daily forecast summary for a single day."""

    date: dt_date = Field(..., description="Forecast date (YYYY-MM-DD)")
    temp_max_c: Optional[float] = Field(None, description="Maximum daily temperature in °C")
    temp_min_c: Optional[float] = Field(None, description="Minimum daily temperature in °C")
    feels_like_max_c: Optional[float] = Field(None, description="Maximum apparent temperature in °C")
    feels_like_min_c: Optional[float] = Field(None, description="Minimum apparent temperature in °C")
    precipitation_sum_mm: Optional[float] = Field(None, description="Total daily precipitation in mm")
    rain_sum_mm: Optional[float] = Field(None, description="Total daily rain in mm")
    snowfall_sum_cm: Optional[float] = Field(None, description="Total daily snowfall in cm")
    precipitation_probability_max_pct: Optional[int] = Field(None, description="Max probability of precipitation in %")
    wind_speed_max_kmh: Optional[float] = Field(None, description="Maximum wind speed in km/h")
    wind_gusts_max_kmh: Optional[float] = Field(None, description="Maximum wind gusts in km/h")
    wind_direction_dominant_deg: Optional[float] = Field(None, description="Dominant wind direction in degrees")
    uv_index_max: Optional[float] = Field(None, description="Maximum UV index")
    weather_code: Optional[int] = Field(None, description="Dominant WMO weather code for the day")
    weather_description: Optional[str] = Field(None, description="Human-readable weather description")
    sunrise: Optional[datetime] = Field(None, description="Sunrise time")
    sunset: Optional[datetime] = Field(None, description="Sunset time")


class HourlyForecast(BaseModel):
    """Hourly forecast slice."""

    valid_at: datetime = Field(..., description="Time of the forecast slice")
    temperature_c: Optional[float] = Field(None, description="Temperature in °C")
    feels_like_c: Optional[float] = Field(None, description="Apparent temperature in °C")
    humidity_pct: Optional[float] = Field(None, description="Relative humidity in %")
    precipitation_mm: Optional[float] = Field(None, description="Precipitation in mm")
    precipitation_probability_pct: Optional[int] = Field(None, description="Precipitation probability in %")
    wind_speed_kmh: Optional[float] = Field(None, description="Wind speed in km/h")
    weather_code: Optional[int] = Field(None, description="WMO weather code")
    weather_description: Optional[str] = Field(None, description="Weather description")
    is_day: Optional[bool] = Field(None, description="True if daytime")


class ForecastTimeline(BaseModel):
    """Universal multi-day/hourly forecast timeline output."""

    source: str = Field(..., description="Data source identifier, e.g. 'open-meteo', 'gfs'")
    issued_at: datetime = Field(..., description="When the data was produced")
    lat: float
    lon: float
    location_name: Optional[str] = None
    timezone: Optional[str] = None
    daily: list[DailyForecast] = Field(default_factory=list, description="Daily forecast entries")
    hourly: Optional[list[HourlyForecast]] = Field(None, description="Hourly forecast slices (optional)")


class LocationMatch(BaseModel):
    """Geocoding result from location resolution."""

    name: str
    lat: float
    lon: float
    country: Optional[str] = None
    country_code: Optional[str] = None
    admin1: Optional[str] = Field(None, description="State / province / region")
    admin2: Optional[str] = Field(None, description="District / county")
    elevation: Optional[float] = None
    timezone: Optional[str] = None
    population: Optional[int] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class AlertRecord(BaseModel):
    """Parsed Common Alerting Protocol (CAP-XML) alert structure.

    Matches NDMA SACHET and IMD official disaster/weather warning feeds.
    """

    alert_id: str = Field(..., description="Unique CAP alert identifier")
    source: str = Field(default="sachet-ndma", description="Source of the alert, e.g. sachet-ndma, imd")
    sender: str = Field(..., description="Agency issuing the alert, e.g. NDMA, IMD, SDMA")
    sent_at: datetime = Field(..., description="Timestamp when the alert was published")
    status: str = Field(default="Actual", description="Status: Actual, Exercise, Draft, Test")
    msg_type: str = Field(default="Alert", description="Message type: Alert, Update, Cancel")
    event: str = Field(..., description="Disaster/weather event name, e.g. Heavy Rain, Cyclone, Flood, Heat Wave")
    urgency: str = Field(default="Expected", description="Urgency: Immediate, Expected, Future, Past, Unknown")
    severity: str = Field(..., description="Severity level: Extreme (Red), Severe (Orange), Moderate (Yellow), Minor, Unknown")
    certainty: str = Field(default="Likely", description="Certainty: Observed, Likely, Possible, Unlikely, Unknown")
    headline: Optional[str] = Field(None, description="Brief summary headline")
    description: Optional[str] = Field(None, description="Detailed hazard details")
    instruction: Optional[str] = Field(None, description="Recommended protective actions for the public")
    effective_at: Optional[datetime] = Field(None, description="Start of hazard window")
    expires_at: Optional[datetime] = Field(None, description="End of hazard window")
    area_desc: Optional[str] = Field(None, description="Affected districts / states description")
    polygon: Optional[list[list[float]]] = Field(None, description="Boundary polygon [[lat, lon], ...]")
    circle: Optional[str] = Field(None, description="Circle format 'lat,lon radius_km'")
    language: str = Field(default="en", description="Alert text language code")


class AlertListResponse(BaseModel):
    """Response model for location alert lookup."""

    location_name: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    count: int = 0
    alerts: list[AlertRecord] = Field(default_factory=list, description="Active alerts matching location")


class ChatRequest(BaseModel):
    """Input to the /chat endpoint."""

    message: str = Field(..., min_length=1, max_length=2000, description="User's weather query")
    language: str = Field(default="en", description="ISO 639-1 language code")
    session_id: Optional[str] = Field(None, description="Session ID for conversation continuity")


class ChatResponse(BaseModel):
    """Output from the /chat endpoint."""

    reply: str = Field(..., description="Natural language response")
    language: str = "en"
    data: Optional[dict] = Field(None, description="Structured weather data, if any")
    session_id: Optional[str] = None
    sources: list[str] = Field(default_factory=list, description="Data sources cited")


class VoiceChatResponse(BaseModel):
    """Output from the /voice/chat endpoint.

    Contains both the text transcript and optional synthesised audio.
    """

    transcript_in: str = Field(..., description="ASR transcript of user's speech input")
    reply_text: str = Field(..., description="Weather response text in user's language")
    reply_audio_base64: Optional[str] = Field(None, description="Base64-encoded WAV/MP3 audio of the reply")
    language: str = Field(default="hi", description="ISO 639-1 language code of the response")
    session_id: Optional[str] = None
    sources: list[str] = Field(default_factory=list, description="Data sources cited")
