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

from app.schemas_and_models.schemas import (
    AlertListResponse,
    ForecastPoint,
    ForecastTimeline,
)

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

DAILY_ITEM_EN = (
    "• {date}: {description}, {min_temp}°C to {max_temp}°C"
    "{rain_info}"
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

DAILY_ITEM_HI = (
    "• {date}: {description}, तापमान {min_temp}°C से {max_temp}°C"
    "{rain_info}"
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


def format_forecast(timeline: ForecastTimeline, language: str = "en") -> str:
    """Fill verified templates with ForecastTimeline data.

    Args:
        timeline: ForecastTimeline with daily weather forecasts.
        language: ISO 639-1 language code ("en" or "hi").

    Returns:
        Formatted multi-line forecast summary.
    """
    loc = timeline.location_name or f"{timeline.lat:.2f}, {timeline.lon:.2f}"
    is_hi = language == "hi"

    lines = [
        f"{loc} के लिए {len(timeline.daily)} दिनों का मौसम पूर्वानुमान:"
        if is_hi
        else f"{len(timeline.daily)}-day weather forecast for {loc}:"
    ]

    item_template = DAILY_ITEM_HI if is_hi else DAILY_ITEM_EN

    for day in timeline.daily:
        rain_info = ""
        if day.precipitation_probability_max_pct is not None:
            if is_hi:
                rain_info = f", बारिश की संभावना: {day.precipitation_probability_max_pct}%"
            else:
                rain_info = f", rain chance: {day.precipitation_probability_max_pct}%"
        elif day.precipitation_sum_mm is not None and day.precipitation_sum_mm > 0:
            if is_hi:
                rain_info = f", बारिश: {day.precipitation_sum_mm} मिमी"
            else:
                rain_info = f", precip: {day.precipitation_sum_mm} mm"

        line = item_template.format(
            date=day.date.strftime("%a, %d %b") if hasattr(day.date, "strftime") else str(day.date),
            description=day.weather_description or ("अज्ञात" if is_hi else "Unknown"),
            min_temp=day.temp_min_c if day.temp_min_c is not None else "N/A",
            max_temp=day.temp_max_c if day.temp_max_c is not None else "N/A",
            rain_info=rain_info,
        )
        lines.append(line)

    return "\n".join(lines)


def format_alerts(alert_response: AlertListResponse, language: str = "en") -> str:
    """Format active disaster / weather alerts into a clear bulleted warning string.

    Args:
        alert_response: AlertListResponse containing matching alerts.
        language: ISO 639-1 language code ("en" or "hi").

    Returns:
        Formatted multi-line alert summary.
    """
    is_hi = language == "hi"
    loc = alert_response.location_name

    if alert_response.count == 0:
        return (
            f"{loc} के लिए कोई सक्रिय आपदा या गंभीर मौसम अलर्ट नहीं है।"
            if is_hi
            else f"No active disaster or severe weather alerts found for {loc}."
        )

    header = (
        f"🚨 **{loc} के लिए सक्रिय आपदा एवं मौसम अलर्ट ({alert_response.count}) — NDMA SACHET / IMD:**"
        if is_hi
        else f"🚨 **Active Weather & Disaster Alerts for {loc} ({alert_response.count}) — NDMA SACHET / IMD:**"
    )
    lines = [header]

    for alert in alert_response.alerts:
        lines.append(f"\n• **[{alert.severity.upper()}] {alert.event}**")
        if alert.headline:
            lines.append(f"  - **Headline:** {alert.headline}")
        if alert.description:
            lines.append(f"  - **Details:** {alert.description}")
        if alert.instruction:
            lines.append(f"  - **Safety Advisory:** {alert.instruction}")
        if alert.expires_at:
            lines.append(f"  - **Valid until:** {alert.expires_at}")

    return "\n".join(lines)
