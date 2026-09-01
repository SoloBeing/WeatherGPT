# Session 03 — Step 01: Forecast Schemas Extension

**Date:** 2026-09-01  
**Goal:** Extend Pydantic schemas with DailyForecast, HourlyForecast, and ForecastTimeline models.

## What was done

1. **Updated `app/schemas_and_models/schemas.py`**:
   - Added `DailyForecast` model with daily weather parameters:
     - `date`: `dt_date`
     - `temp_max_c`, `temp_min_c`, `feels_like_max_c`, `feels_like_min_c`
     - `precipitation_sum_mm`, `rain_sum_mm`, `snowfall_sum_cm`
     - `precipitation_probability_max_pct`
     - `wind_speed_max_kmh`, `wind_gusts_max_kmh`, `wind_direction_dominant_deg`
     - `uv_index_max`, `weather_code`, `weather_description`, `sunrise`, `sunset`
   - Added `HourlyForecast` model for granular hourly slices.
   - Added `ForecastTimeline` universal model containing `source`, `issued_at`, `lat`, `lon`, `location_name`, `timezone`, `daily: list[DailyForecast]`, and optional `hourly`.

## Exact commands & verification

```bash
uv run python -c "from app.schemas_and_models.schemas import DailyForecast, HourlyForecast, ForecastTimeline; print('Schemas OK')"
```

## Notable decisions

- Imported `from datetime import date as dt_date` to prevent Pydantic field name vs type annotation collisions on `date: dt_date`.
- Kept optional fields with `None` defaults for clean JSON serialization.

## Files changed

- `MOD app/schemas_and_models/schemas.py`
