"""
get_agricultural_advisory(crop, stage, location) — ICAR / IMD Agromet Advisory Engine.

Combines deterministic multi-day NWP forecasts with phenological crop-stage
rules (aligned with ICAR-CRIDA and IMD Gramin Krishi Mausam Seva) to generate
practical farming advice: irrigation scheduling, spray windows, harvest timing,
and pest/disease early warnings.
"""

from datetime import datetime, timezone
import json
import logging
from typing import Optional

from app.data_sources.openmeteo import openmeteo_client
from app.models.schemas import CropAdvisoryReport
from app.tools.location_resolver import resolve_location

logger = logging.getLogger(__name__)

# Major Indian crop pest/disease vulnerability profiles
CROP_PEST_PROFILES: dict[str, list[str]] = {
    "RICE": [
        "Monitor for Brown Plant Hopper (BPH) at base of plants; drain field for 2-3 days if population exceeds ETL.",
        "Warm humid weather favours Bacterial Leaf Blight and Blast; avoid excess urea application.",
    ],
    "PADDY": [
        "Monitor for Brown Plant Hopper (BPH) at base of plants; drain field for 2-3 days if population exceeds ETL.",
        "Warm humid weather favours Bacterial Leaf Blight and Blast; avoid excess urea application.",
    ],
    "WHEAT": [
        "Regularly survey for Yellow / Brown Rust on leaf blades during cool morning dew periods.",
        "Monitor for Aphid infestation on earheads during grain filling; spray neem-based formulations if detected.",
    ],
    "COTTON": [
        "Scout for Whitefly and Pink Bollworm; install pheromone traps @ 5 traps/ha.",
        "Prevent water stagnation around roots to curb Parawilt / root rot.",
    ],
    "MUSTARD": [
        "Overcast and humid weather is conducive to Mustard Aphid (Lipaphis erysimi); inspect 10cm terminal shoots.",
        "Watch for Alternaria blight spots on lower foliage.",
    ],
    "PULSES": [
        "Monitor for Pod Borer (Helicoverpa armigera) at flowering and pod development stages.",
        "Ensure field drainage to avoid root rot and wilt complex.",
    ],
    "SUGARCANE": [
        "Propping and earthing up recommended if gusty winds are forecast to prevent lodging.",
        "Monitor for Top Borer and Pyrilla in ratoon crops.",
    ],
}


async def get_agricultural_advisory(
    crop: str,
    stage: str,
    location: str,
) -> str:
    """Generate deterministic agro-meteorological advisory for Indian farming communities.

    Args:
        crop: Crop name (e.g. "Rice", "Wheat", "Cotton", "Mustard", "Pulses", "Sugarcane").
        stage: Growth stage (e.g. "Sowing", "Vegetative", "Flowering", "Maturity", "Harvesting").
        location: Farming district, taluk, or village name (e.g. "Guntur", "Karnal", "Wardha", "Bhatinda", "Coimbatore").

    Returns:
        JSON string containing CropAdvisoryReport.
    """
    logger.info("Generating agromet advisory for crop='%s', stage='%s', location='%s'", crop, stage, location)

    # 1. Resolve location
    lat = 28.6139
    lon = 77.2090
    loc_name = location

    try:
        matches = await resolve_location(location)
        if matches:
            lat = matches[0].lat
            lon = matches[0].lon
            loc_name = matches[0].name
            if matches[0].admin1:
                loc_name += f", {matches[0].admin1}"
    except Exception as exc:
        logger.warning("Advisory geocoding fallback for '%s': %s", location, exc)

    # 2. Fetch 5-day forecast
    now = datetime.now(timezone.utc)
    rain_sum = 0.0
    t_max = 32.0
    t_min = 22.0
    wind_max = 12.0
    data_quality = "verified"

    try:
        timeline = await openmeteo_client.fetch_forecast(lat=lat, lon=lon, days=5)
        if timeline.daily:
            rain_sum = round(sum(d.precipitation_sum_mm or 0.0 for d in timeline.daily), 1)
            temps_max = [d.temp_max_c for d in timeline.daily if d.temp_max_c is not None]
            temps_min = [d.temp_min_c for d in timeline.daily if d.temp_min_c is not None]
            winds = [d.wind_speed_max_kmh for d in timeline.daily if d.wind_speed_max_kmh is not None]

            if temps_max:
                t_max = round(max(temps_max), 1)
            if temps_min:
                t_min = round(min(temps_min), 1)
            if winds:
                wind_max = round(max(winds), 1)
    except Exception as exc:
        logger.warning("Forecast retrieval error for advisory: %s. Using climatological sandbox.", exc)
        data_quality = "synthetic"
        rain_sum = 2.5
        t_max = 33.0
        t_min = 23.0

    # 3. Rule-based Agro-Meteorological Evaluation (ICAR / IMD)
    crop_upper = crop.strip().upper()
    stage_lower = stage.strip().lower()

    # Irrigation rule
    if rain_sum >= 15.0:
        irrigation_adv = (
            f"Postpone irrigation. Significant cumulative rainfall ({rain_sum} mm) is forecast over the next 5 days. "
            "Clear field drainage channels to prevent water stagnation in the root zone."
        )
    elif rain_sum >= 5.0:
        irrigation_adv = (
            f"Withhold scheduled irrigation temporarily. Light to moderate showers ({rain_sum} mm) expected. "
            "Check topsoil moisture before applying supplementary water."
        )
    elif t_max >= 35.0:
        irrigation_adv = (
            f"High thermal stress expected (max temperature {t_max}°C) with dry conditions ({rain_sum} mm rain). "
            f"Apply light and frequent irrigation during evening or early morning hours to maintain {crop} canopy turgor."
        )
    else:
        irrigation_adv = (
            f"Dry weather conditions ({rain_sum} mm rain, max {t_max}°C). "
            f"Maintain standard irrigation intervals suited for {crop} at {stage} stage."
        )

    # Spraying rule (pesticides / herbicides / foliar micronutrients)
    if rain_sum >= 5.0:
        spray_adv = (
            f"Do NOT spray pesticides or foliar nutrients. Impending rainfall ({rain_sum} mm) will wash off chemicals, "
            "resulting in economic loss and environmental runoff."
        )
    elif wind_max >= 20.0:
        spray_adv = (
            f"Avoid spraying chemical solutions during peak hours due to high wind drift risk (gusts up to {wind_max:.1f} km/h). "
            "Spray strictly during calm morning hours."
        )
    else:
        spray_adv = (
            "Weather conditions are highly favourable for plant protection spraying and foliar feeding. "
            "Optimal spray window: 07:00 AM - 10:30 AM."
        )

    # Field operations & harvest rule
    if "harvest" in stage_lower or "matur" in stage_lower:
        if rain_sum >= 10.0:
            field_adv = (
                f"URGENT HARVEST ADVISORY: {rain_sum} mm rain expected. Expedite harvesting of physiologically mature crop "
                "immediately. Store harvested grain/produce under waterproof tarpaulins or elevated thrashing floors."
            )
        else:
            field_adv = "Optimal clear weather for harvesting, threshing, and open-sun grain moisture reduction."
    elif "sow" in stage_lower or "plant" in stage_lower:
        if rain_sum >= 25.0:
            field_adv = "Postpone sowing until heavy rain spell clears to prevent seed burial and seedling rot."
        else:
            field_adv = "Favourable soil moisture regime for seedbed preparation, harrowing, and certified seed sowing."
    else:
        field_adv = "Favourable window for manual weeding, hoeing, and top-dressing with nitrogenous fertilizer."

    # Crop-specific pest warnings
    alerts: list[str] = []
    for k, v in CROP_PEST_PROFILES.items():
        if k in crop_upper or crop_upper in k:
            alerts.extend(v)
            break

    if not alerts:
        alerts.append(f"Inspect {crop} canopy regularly for sucking pests and leaf spot diseases.")
    if t_max >= 36.0:
        alerts.append("Heat stress warning: Monitor for flower drop and reduced pollen viability.")

    report = CropAdvisoryReport(
        source="ICAR / IMD Agromet Engine",
        data_quality=data_quality,
        crop=crop.strip().title(),
        stage=stage.strip().title(),
        location_name=loc_name,
        issued_at=now,
        forecast_rain_sum_mm=rain_sum,
        forecast_temp_max_c=t_max,
        forecast_temp_min_c=t_min,
        irrigation_advisory=irrigation_adv,
        spray_advisory=spray_adv,
        field_operation_advisory=field_adv,
        pest_disease_alerts=alerts,
    )
    return report.model_dump_json(exclude_none=True)
