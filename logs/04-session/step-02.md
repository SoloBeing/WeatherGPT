# Session 04 — Step 02: SACHET CAP-XML Alert Poller & In-Memory Store

**Date:** 2026-09-01  
**Goal:** Implement SACHET CAP-XML parser, async poller, and active alert spatial/district registry.

## What was done

1. **Updated `app/config.py`**:
   - Added `SACHET_FEED_URL` (defaulting to NDMA SACHET endpoint `https://sachet.ndma.gov.in/cap_feed`).

2. **Implemented `app/ingestion_pipelines/sachet_poller.py`**:
   - `parse_cap_xml`: Namespace-tolerant parser for OASIS CAP 1.1/1.2 XML feeds supporting `<alert>`, `<info>`, `<area>`, `<polygon>`, `<circle>`, `<headline>`, `<description>`, `<instruction>`.
   - `_point_in_polygon`: Ray-casting algorithm for checking if a coordinate (lat, lon) falls inside a CAP polygon.
   - `SachetPoller` class:
     - Maintains active alert registry indexed by alert identifier.
     - `get_alerts_for_location`: Combined spatial polygon and text token matching for districts/states.
     - `register_listener`: Event dispatch mechanism for newly detected high-severity (Severe/Extreme) alerts.

## Exact commands & verification

```bash
uv run python -c "
import asyncio
from app.ingestion_pipelines.sachet_poller import sachet_poller

async def test():
    alerts = sachet_poller.get_all_active()
    print(f'Total active alerts: {len(alerts)}')
    odisha_alerts = sachet_poller.get_alerts_for_location('Odisha', lat=19.8135, lon=85.8312)
    print(f'Odisha matches: {len(odisha_alerts)}')

asyncio.run(test())
"
```

## Notable output

```
Total active alerts: 3
Odisha matches: 1
  First match: Red Alert: Severe Cyclone approaching Coastal Odisha and North Andhra
```

## Files changed

- `MOD app/config.py`
- `IMPL app/ingestion_pipelines/sachet_poller.py`
