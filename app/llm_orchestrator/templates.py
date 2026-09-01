"""
Multilingual Response Templates — Factual core in verified templates.

From the spec:
  "Don't translate free-form LLM prose — errors compound and you can't
   audit them. Instead: tools return structured values → fill a template
   per language for the factual core → use the LLM only for surrounding
   conversational glue."

Example:
  "{district} में कल {rain_mm} मिमी बारिश की संभावना है"

Templates are verifiable, instant, and never invent a number.
"""

from app.schemas_and_models.schemas import ForecastPoint

# ---------------------------------------------------------------------------
# English templates
# ---------------------------------------------------------------------------

CURRENT_WEATHER_EN = (
    "Currently in {location}: {description}, {temp}°C "
    "(feels like {feels_like}°C). "
    "Humidity: {humidity}%. "
    "Wind: {wind_speed} km/h. "
    "Pressure: {pressure} hPa. "
    "Cloud cover: {cloud_cover}%."
)

# ---------------------------------------------------------------------------
# Hindi templates
# ---------------------------------------------------------------------------

CURRENT_WEATHER_HI = (
    "{location} में अभी: {description}, तापमान {temp}°C "
    "(महसूस {feels_like}°C)। "
    "नमी: {humidity}%। "
    "हवा: {wind_speed} किमी/घंटा। "
    "दबाव: {pressure} hPa। "
    "बादल: {cloud_cover}%।"
)


def format_current_weather(point: ForecastPoint, language: str = "en") -> str:
    """Fill a verified template with ForecastPoint data.

    The factual core is template-driven — no LLM involved.
    The LLM only adds conversational glue around this.

    Args:
        point: ForecastPoint with current weather data.
        language: ISO 639-1 language code ("en" or "hi").

    Returns:
        Formatted string with weather facts.
    """
    template = CURRENT_WEATHER_HI if language == "hi" else CURRENT_WEATHER_EN

    return template.format(
        location=point.location_name or f"{point.lat:.2f}, {point.lon:.2f}",
        description=point.weather_description or "Unknown conditions",
        temp=point.temperature_c if point.temperature_c is not None else "N/A",
        feels_like=point.feels_like_c if point.feels_like_c is not None else "N/A",
        humidity=point.humidity_pct if point.humidity_pct is not None else "N/A",
        wind_speed=point.wind_speed_kmh if point.wind_speed_kmh is not None else "N/A",
        pressure=point.pressure_hpa if point.pressure_hpa is not None else "N/A",
        cloud_cover=point.cloud_cover_pct if point.cloud_cover_pct is not None else "N/A",
    )
