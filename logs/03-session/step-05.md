# Session 03 — Step 05: LLM Tool Registration & Multilingual Forecast Templates

**Date:** 2026-09-01  
**Goal:** Register `get_forecast` in LLM tool calling schema and add English/Hindi forecast templates.

## What was done

1. **Updated `app/llm_orchestrator/templates.py`**:
   - Added `format_forecast(timeline, language)` generating factual, structured daily breakdown lines.
   - Built `DAILY_ITEM_EN` and `DAILY_ITEM_HI` verified templates with rain chances, min/max temperatures, and weather descriptions.

2. **Updated `app/llm_orchestrator/router.py`**:
   - Added `get_forecast` definition to `TOOLS` (parameters: `location` [required], `days` [optional integer, 1 to 16, default 5]).
   - Added `get_forecast` to `_TOOL_DISPATCH` mapping.
   - Updated `SYSTEM_PROMPT` to guide the model on dispatching `get_current_weather` for current conditions vs `get_forecast` for future/multi-day queries.

## Exact commands & verification

```bash
uv run python -c "from app.llm_orchestrator.router import TOOLS, _TOOL_DISPATCH; print('Registered tools:', list(_TOOL_DISPATCH.keys()))"
```

## Notable output

```
Registered tools: ['get_current_weather', 'get_forecast']
```

## Files changed

- `MOD app/llm_orchestrator/templates.py`
- `MOD app/llm_orchestrator/router.py`
