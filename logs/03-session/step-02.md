# Session 03 — Step 02: Open-Meteo Forecast Extension

**Date:** 2026-09-01  
**Goal:** Implement `fetch_forecast` method on BaseDataSource and OpenMeteoClient.

## What was done

1. **Updated `app/data_sources/base.py`**:
   - Added abstract method `fetch_forecast(lat, lon, days=7, include_hourly=False) -> ForecastTimeline` to `BaseDataSource`.

2. **Updated `app/data_sources/openmeteo.py`**:
   - Added `_DAILY_PARAMS` (15 parameters including max/min temperatures, precipitation sums, rain probability, wind, UV, sunrise/sunset).
   - Added `_HOURLY_PARAMS` (8 parameters for detailed slices).
   - Implemented `fetch_forecast` method mapping Open-Meteo `/forecast` responses to `ForecastTimeline` and translating WMO weather codes.

## Exact commands & verification

```bash
uv run python -c "
import asyncio
from app.data_sources.openmeteo import OpenMeteoClient

async def test():
    client = OpenMeteoClient()
    try:
        f = await client.fetch_forecast(28.6139, 77.2090, days=3)
        print('Forecast source:', f.source)
        print('Daily count:', len(f.daily))
        for d in f.daily:
            print(f'  {d.date}: {d.temp_min_c}°C - {d.temp_max_c}°C, {d.weather_description}, rain prob: {d.precipitation_probability_max_pct}%')
    finally:
        await client.close()

asyncio.run(test())
"
```

## Notable output

```
Forecast source: open-meteo
Daily count: 3
  2026-09-01: 27.4°C - 34.3°C, Slight rain showers, rain prob: 94%
  2026-09-02: 26.2°C - 31.0°C, Slight rain showers, rain prob: 98%
  2026-09-03: 25.8°C - 31.8°C, Thunderstorm with slight hail, rain prob: 71%
```

## Files changed

- `MOD app/data_sources/base.py`
- `MOD app/data_sources/openmeteo.py`
