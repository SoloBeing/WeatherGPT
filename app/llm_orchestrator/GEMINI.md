# llm_orchestrator — Context

## Role
The brain: intent classification → tool dispatch → response phrasing.

## Sacred Rule
**The LLM never computes or recalls weather.** It only:
1. Parses intent (small model, ~100ms)
2. Calls tools (deterministic)
3. Phrases tool output (big model, temp 0.2)

## Files
- `router.py` — Main orchestrator wiring intent → tools → phrased response
- `intent.py` — Small/fast model (Haiku-class) for intent classification
- `templates.py` — Multilingual verified templates for factual core

## Intent Categories
current_weather, forecast, alerts, climatology, advisory, chit_chat, definition, greeting, unclear

## Multilingual Strategy
- Tools return structured values
- Fill verified template per language for factual core (numbers never invented)
- LLM only for surrounding conversational glue
- Bhashini NMT handles anything templates miss
