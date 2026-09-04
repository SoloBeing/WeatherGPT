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

Supported template languages: en, hi, ta, te, bn, mr
Other languages fall back to English template + Bhashini NMT translation.
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

# ---------------------------------------------------------------------------
# Tamil (ta) templates
# ---------------------------------------------------------------------------

CURRENT_WEATHER_TA = (
    "{location} இல் தற்போது: {description}, வெப்பநிலை {temp}°C "
    "(உணரும் வெப்பநிலை {feels_like}°C). "
    "ஈரப்பதம்: {humidity}%. "
    "காற்று: {wind_speed} கிமீ/மணி. "
    "அழுத்தம்: {pressure} hPa. "
    "மேக மூட்டம்: {cloud_cover}%."
)

DAILY_ITEM_TA = (
    "• {date}: {description}, {min_temp}°C முதல் {max_temp}°C வரை"
    "{rain_info}"
)

# ---------------------------------------------------------------------------
# Telugu (te) templates
# ---------------------------------------------------------------------------

CURRENT_WEATHER_TE = (
    "{location} లో ప్రస్తుతం: {description}, ఉష్ణోగ్రత {temp}°C "
    "(అనిపించే ఉష్ణోగ్రత {feels_like}°C). "
    "తేమ: {humidity}%. "
    "గాలి: {wind_speed} కి.మీ/గంట. "
    "వాయుపీడనం: {pressure} hPa. "
    "మేఘావృతం: {cloud_cover}%."
)

DAILY_ITEM_TE = (
    "• {date}: {description}, {min_temp}°C నుండి {max_temp}°C వరకు"
    "{rain_info}"
)

# ---------------------------------------------------------------------------
# Bengali (bn) templates
# ---------------------------------------------------------------------------

CURRENT_WEATHER_BN = (
    "{location}-এ এখন: {description}, তাপমাত্রা {temp}°C "
    "(অনুভূত তাপমাত্রা {feels_like}°C)। "
    "আর্দ্রতা: {humidity}%। "
    "বাতাস: {wind_speed} কিমি/ঘণ্টা। "
    "চাপ: {pressure} hPa। "
    "মেঘাচ্ছন্নতা: {cloud_cover}%।"
)

DAILY_ITEM_BN = (
    "• {date}: {description}, {min_temp}°C থেকে {max_temp}°C"
    "{rain_info}"
)

# ---------------------------------------------------------------------------
# Marathi (mr) templates
# ---------------------------------------------------------------------------

CURRENT_WEATHER_MR = (
    "{location} मध्ये सध्या: {description}, तापमान {temp}°C "
    "(जाणवते {feels_like}°C). "
    "आर्द्रता: {humidity}%. "
    "वारा: {wind_speed} किमी/तास. "
    "दाब: {pressure} hPa. "
    "ढगाळपणा: {cloud_cover}%."
)

DAILY_ITEM_MR = (
    "• {date}: {description}, {min_temp}°C ते {max_temp}°C"
    "{rain_info}"
)

# ---------------------------------------------------------------------------
# Template registry — maps language code to (current_weather, daily_item) templates
# ---------------------------------------------------------------------------

_CURRENT_WEATHER_TEMPLATES: dict[str, str] = {
    "en": CURRENT_WEATHER_EN,
    "hi": CURRENT_WEATHER_HI,
    "ta": CURRENT_WEATHER_TA,
    "te": CURRENT_WEATHER_TE,
    "bn": CURRENT_WEATHER_BN,
    "mr": CURRENT_WEATHER_MR,
}

_DAILY_ITEM_TEMPLATES: dict[str, str] = {
    "en": DAILY_ITEM_EN,
    "hi": DAILY_ITEM_HI,
    "ta": DAILY_ITEM_TA,
    "te": DAILY_ITEM_TE,
    "bn": DAILY_ITEM_BN,
    "mr": DAILY_ITEM_MR,
}

# Rain info snippets per language
_RAIN_CHANCE_FMT: dict[str, str] = {
    "en": ", rain chance: {pct}%",
    "hi": ", बारिश की संभावना: {pct}%",
    "ta": ", மழை வாய்ப்பு: {pct}%",
    "te": ", వర్షం అవకాశం: {pct}%",
    "bn": ", বৃষ্টির সম্ভাবনা: {pct}%",
    "mr": ", पावसाची शक्यता: {pct}%",
}

_PRECIP_FMT: dict[str, str] = {
    "en": ", precip: {mm} mm",
    "hi": ", बारिश: {mm} मिमी",
    "ta": ", மழை: {mm} மிமீ",
    "te": ", వర్షపాతం: {mm} మిమీ",
    "bn": ", বৃষ্টি: {mm} মিমি",
    "mr": ", पाऊस: {mm} मिमी",
}

_UNKNOWN_LABELS: dict[str, str] = {
    "en": "Unknown",
    "hi": "अज्ञात",
    "ta": "தெரியாது",
    "te": "తెలియదు",
    "bn": "অজানা",
    "mr": "अज्ञात",
}

# Forecast header per language
_FORECAST_HEADER: dict[str, str] = {
    "en": "{days}-day weather forecast for {loc}:",
    "hi": "{loc} के लिए {days} दिनों का मौसम पूर्वानुमान:",
    "ta": "{loc} க்கான {days} நாள் வானிலை முன்னறிவிப்பு:",
    "te": "{loc} కోసం {days} రోజుల వాతావరణ సూచన:",
    "bn": "{loc}-এর জন্য {days} দিনের আবহাওয়া পূর্বাভাস:",
    "mr": "{loc} साठी {days} दिवसांचा हवामान अंदाज:",
}

# Alert strings per language
_NO_ALERTS: dict[str, str] = {
    "en": "No active disaster or severe weather alerts found for {loc}.",
    "hi": "{loc} के लिए कोई सक्रिय आपदा या गंभीर मौसम अलर्ट नहीं है।",
    "ta": "{loc} க்கு செயலில் உள்ள பேரிடர் அல்லது கடுமையான வானிலை எச்சரிக்கை இல்லை.",
    "te": "{loc} కోసం ఎటువంటి చురుకైన విపత్తు లేదా తీవ్ర వాతావరణ హెచ్చరికలు లేవు.",
    "bn": "{loc}-এর জন্য কোনো সক্রিয় দুর্যোগ বা গুরুতর আবহাওয়া সতর্কতা নেই।",
    "mr": "{loc} साठी कोणत्याही सक्रिय आपत्ती किंवा गंभीर हवामान अलर्ट नाहीत.",
}

_ALERTS_HEADER: dict[str, str] = {
    "en": "🚨 **Active Weather & Disaster Alerts for {loc} ({count}) — NDMA SACHET / IMD:**",
    "hi": "🚨 **{loc} के लिए सक्रिय आपदा एवं मौसम अलर्ट ({count}) — NDMA SACHET / IMD:**",
    "ta": "🚨 **{loc} க்கான செயலில் உள்ள பேரிடர் எச்சரிக்கைகள் ({count}) — NDMA SACHET / IMD:**",
    "te": "🚨 **{loc} కోసం చురుకైన విపత్తు హెచ్చరికలు ({count}) — NDMA SACHET / IMD:**",
    "bn": "🚨 **{loc}-এর জন্য সক্রিয় দুর্যোগ সতর্কতা ({count}) — NDMA SACHET / IMD:**",
    "mr": "🚨 **{loc} साठी सक्रिय आपत्ती इशारे ({count}) — NDMA SACHET / IMD:**",
}


def format_current_weather(point: ForecastPoint, language: str = "en") -> str:
    """Fill a verified template with ForecastPoint data.

    The factual core is template-driven — no LLM involved.
    The LLM only adds conversational glue around this.

    Falls back to English template for unsupported languages.

    Args:
        point: ForecastPoint with current weather data.
        language: ISO 639-1 language code.

    Returns:
        Formatted string with weather facts.
    """
    template = _CURRENT_WEATHER_TEMPLATES.get(language, CURRENT_WEATHER_EN)

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

    Supports en, hi, ta, te, bn, mr. Falls back to English for others.

    Args:
        timeline: ForecastTimeline with daily weather forecasts.
        language: ISO 639-1 language code.

    Returns:
        Formatted multi-line forecast summary.
    """
    loc = timeline.location_name or f"{timeline.lat:.2f}, {timeline.lon:.2f}"
    lang = language if language in _FORECAST_HEADER else "en"

    header = _FORECAST_HEADER[lang].format(days=len(timeline.daily), loc=loc)
    lines = [header]

    item_template = _DAILY_ITEM_TEMPLATES.get(lang, DAILY_ITEM_EN)
    rain_chance_fmt = _RAIN_CHANCE_FMT.get(lang, _RAIN_CHANCE_FMT["en"])
    precip_fmt = _PRECIP_FMT.get(lang, _PRECIP_FMT["en"])
    unknown = _UNKNOWN_LABELS.get(lang, "Unknown")

    for day in timeline.daily:
        rain_info = ""
        if day.precipitation_probability_max_pct is not None:
            rain_info = rain_chance_fmt.format(pct=day.precipitation_probability_max_pct)
        elif day.precipitation_sum_mm is not None and day.precipitation_sum_mm > 0:
            rain_info = precip_fmt.format(mm=day.precipitation_sum_mm)

        line = item_template.format(
            date=day.date.strftime("%a, %d %b") if hasattr(day.date, "strftime") else str(day.date),
            description=day.weather_description or unknown,
            min_temp=day.temp_min_c if day.temp_min_c is not None else "N/A",
            max_temp=day.temp_max_c if day.temp_max_c is not None else "N/A",
            rain_info=rain_info,
        )
        lines.append(line)

    return "\n".join(lines)


def format_alerts(alert_response: AlertListResponse, language: str = "en") -> str:
    """Format active disaster / weather alerts into a clear bulleted warning string.

    Supports en, hi, ta, te, bn, mr. Falls back to English for others.

    Args:
        alert_response: AlertListResponse containing matching alerts.
        language: ISO 639-1 language code.

    Returns:
        Formatted multi-line alert summary.
    """
    lang = language if language in _NO_ALERTS else "en"
    loc = alert_response.location_name

    if alert_response.count == 0:
        return _NO_ALERTS[lang].format(loc=loc)

    header = _ALERTS_HEADER[lang].format(loc=loc, count=alert_response.count)
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
