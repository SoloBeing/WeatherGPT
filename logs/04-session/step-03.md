# Session 04 — Step 03: `get_alerts` Weather Tool & Location Resolver Gazetteer

**Date:** 2026-09-01  
**Goal:** Implement `get_alerts` tool with spatial/district lookup and extend location resolver with Indian state gazetteer.

## What was done

1. **Updated `app/weather_tools/location_resolver.py`**:
   - Added `INDIAN_STATES_GAZETTEER` mapping all 36 Indian states and union territories to administrative coordinates for instant, high-confidence (1.0) resolution.

2. **Implemented `app/weather_tools/alerts_tool.py`**:
   - `get_alerts(location: str, min_severity: Optional[str] = None) -> str`:
     - Resolves location name to coordinates and administrative metadata.
     - Queries `SachetPoller` for active CAP alerts via spatial polygon and textual area matching.
     - Returns serialized `AlertListResponse` JSON for LLM orchestrator.

## Exact commands & verification

```bash
uv run python -c "
import asyncio
from app.weather_tools.alerts_tool import get_alerts

async def test():
    res = await get_alerts('Odisha')
    print('Odisha alerts count:', res.count('alert_id'))

asyncio.run(test())
"
```

## Notable output

```
Odisha alerts count: 1
{"location_name":"Odisha, Odisha, India","lat":20.95,"lon":85.09,"count":1,"alerts":[{"alert_id":"SACHET-NDMA-2026-CY-0891",...
```

## Files changed

- `MOD app/weather_tools/location_resolver.py`
- `IMPL app/weather_tools/alerts_tool.py`
