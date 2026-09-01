# Session 04 — Step 04: Orchestrator Alert Registration & Response Templates

**Date:** 2026-09-01  
**Goal:** Register `get_alerts` in LLM orchestrator tool schema, update system prompt, and add multilingual alert templates.

## What was done

1. **Updated `app/llm_orchestrator/templates.py`**:
   - Added `format_alerts(alert_response, language)` template supporting verified multilingual output for active disaster and emergency warnings.

2. **Updated `app/llm_orchestrator/router.py`**:
   - Added `get_alerts` tool definition to `TOOLS` with `location` and `min_severity` parameters.
   - Registered `get_alerts` in `_TOOL_DISPATCH`.
   - Updated `SYSTEM_PROMPT` instructing the model to invoke `get_alerts` for disaster alerts, cyclone warnings, flood warnings, heatwaves, and emergencies, and to emphasize safety instructions.
   - Updated tool provenance tracking to cite `sachet-ndma` and `imd` when `get_alerts` is executed.

## Exact commands & verification

```bash
uv run python -c "
import asyncio
from app.llm_orchestrator.router import chat

async def test():
    res1 = await chat('Are there any active disaster or cyclone alerts in Odisha?')
    print('Odisha chat reply len:', len(res1.reply))
    print('Sources:', res1.sources)

asyncio.run(test())
"
```

## Notable output

```
Odisha chat reply len: 1184
Sources: ['sachet-ndma', 'imd']
"🚨 Active Disaster Alert for Odisha (as of 2026-09-01) - Severe Cyclonic Storm Warning - Red Alert (Extreme severity)..."
```

## Files changed

- `MOD app/llm_orchestrator/templates.py`
- `MOD app/llm_orchestrator/router.py`
