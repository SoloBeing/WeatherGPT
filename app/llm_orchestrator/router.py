"""
LLM Router — The orchestrator that ties intent → tools → response.

Key principle from the spec:
  "The LLM never computes or recalls weather. It only (a) parses the
   query into a structured intent, (b) calls tools, (c) phrases the
   tool output in the user's language. Every number comes from a
   deterministic service."

Flow:
  1. Small/fast model classifies intent (~100ms)
  2. If needs numbers → tool call(s)
  3. If chit-chat/definition → RAG over IMD docs
  4. Big model phrases the structured JSON into prose (temp 0.2)
"""

import json
import logging
import uuid
from typing import Optional

import litellm

from app.config import settings
from app.database.redis_cache import cache
from app.models.schemas import ChatResponse
from app.weather_tools.alerts_tool import get_alerts
from app.weather_tools.current import get_current_weather
from app.weather_tools.forecast import get_forecast

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt — enforces the "LLM never computes weather" boundary
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are WeatherGPT, a helpful and friendly weather assistant specialising in India.

## RULES — read these carefully:
1. You NEVER make up, estimate, or recall weather data or disaster alerts from memory.
   Every weather number and disaster alert MUST come from a tool call.
2. When a user asks about current weather, call `get_current_weather`.
3. When a user asks about upcoming weather, tomorrow, multi-day, 3-day, 5-day, 7-day,
   or weekend forecasts, call `get_forecast`.
4. When a user asks about disaster alerts, warnings, cyclones, floods, heavy rain alerts,
   heatwaves, thunderstorms, or emergencies, call `get_alerts`.
5. If a user refers to a location mentioned earlier in the conversation (e.g. "any alerts there?"),
   use that location in your tool call.
6. After receiving tool results, present the data conversationally and clearly:
   - For multi-day forecasts: summarize each day with date/day, conditions, min-max temps, and rain probability.
   - For disaster alerts: highlight the severity level (Red/Extreme, Orange/Severe, Yellow/Moderate), affected areas, and safety instructions clearly.
   - Always mention the data source (e.g. "According to NDMA SACHET / IMD..." or "According to Open-Meteo...").
7. If a tool returns an error or no alerts found, inform the user honestly.
8. For greetings, chit-chat, or non-weather questions, respond naturally without calling tools.
9. If the user speaks in Hindi or another Indian language, respond in that language while keeping
   numbers and units in standard form.
10. Be concise, well-structured, and helpful. Use emoji sparingly to enhance readability (🚨 🌤️ ☀️ 🌧️ etc.).
"""

# ---------------------------------------------------------------------------
# Tool definitions (OpenAI function-calling format, used by litellm)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_weather",
            "description": (
                "Get current weather conditions for a location. "
                "Call this whenever the user asks about current weather, "
                "temperature, or conditions right now in a city or place."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": (
                            "City or place name, e.g. 'Delhi', 'Mumbai', "
                            "'Jaipur', 'Bengaluru'. Use the common English "
                            "name for Indian cities."
                        ),
                    },
                },
                "required": ["location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_forecast",
            "description": (
                "Get multi-day weather forecast (daily high/low temperatures, rain probability, "
                "precipitation, wind speed, weather conditions) for a location. "
                "Call this whenever the user asks about upcoming weather, tomorrow, "
                "the next few days, 3-day/5-day/7-day/weekly forecast, or weekend weather."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": (
                            "City or place name, e.g. 'Delhi', 'Mumbai', "
                            "'Jaipur', 'Bengaluru'. Use the common English "
                            "name for Indian cities."
                        ),
                    },
                    "days": {
                        "type": "integer",
                        "description": "Number of forecast days (1 to 16, default 5)",
                        "default": 5,
                    },
                },
                "required": ["location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_alerts",
            "description": (
                "Get active disaster and weather alerts/warnings (e.g. cyclone, heavy rain, flood, "
                "thunderstorm, lightning, heatwave, tsunami warnings) issued by NDMA SACHET or IMD "
                "for a city, district, or state."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": (
                            "City, district, or state name, e.g. 'Odisha', 'Mumbai', 'Kerala', "
                            "'Assam', 'Delhi', 'Jaipur'."
                        ),
                    },
                    "min_severity": {
                        "type": "string",
                        "enum": ["Minor", "Moderate", "Severe", "Extreme"],
                        "description": "Optional minimum alert severity filter.",
                    },
                },
                "required": ["location"],
            },
        },
    },
]

# Map tool names → async callables
_TOOL_DISPATCH: dict = {
    "get_current_weather": get_current_weather,
    "get_forecast": get_forecast,
    "get_alerts": get_alerts,
}

# Maximum tool-calling rounds to prevent infinite loops
_MAX_TOOL_ROUNDS = 5

# Maximum conversation history messages retained per session
_MAX_HISTORY_MESSAGES = 10

# In-memory session store fallback
_IN_MEMORY_SESSIONS: dict[str, list[dict]] = {}


async def _get_session_history(session_id: str) -> list[dict]:
    """Retrieve recent conversation history for a session."""
    # Try Redis first
    cache_key = f"session:{session_id}"
    history = await cache.get_json(cache_key)
    if isinstance(history, list):
        return history

    # Fallback to in-memory store
    return _IN_MEMORY_SESSIONS.get(session_id, [])


async def _save_session_history(session_id: str, history: list[dict]) -> None:
    """Save trimmed conversation history for a session."""
    trimmed = history[-_MAX_HISTORY_MESSAGES:]
    _IN_MEMORY_SESSIONS[session_id] = trimmed

    # Also persist to Redis (TTL 2 hours)
    cache_key = f"session:{session_id}"
    await cache.set_json(cache_key, trimmed, ttl=7200)


async def chat(
    message: str,
    language: str = "en",
    session_id: Optional[str] = None,
) -> ChatResponse:
    """Process a user message through the LLM orchestrator with session support.

    Flow:
        1. Retrieve session history (if session_id provided or generated)
        2. Construct prompt: SYSTEM_PROMPT + session history + new user message
        3. Execute tool-calling loop (litellm acompletion)
        4. Save user turn and assistant reply to session history
        5. Return ChatResponse

    Args:
        message: The user's text message.
        language: ISO 639-1 language code.
        session_id: Optional session identifier for multi-turn conversations.

    Returns:
        ChatResponse with the LLM's natural-language reply and session_id.
    """
    sid = session_id or str(uuid.uuid4())
    history = await _get_session_history(sid)

    # Build message list for LLM: system prompt + past conversation + new message
    llm_messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    llm_messages.extend(history)
    llm_messages.append({"role": "user", "content": message})

    sources: list[str] = []

    # --- Tool-calling loop ---
    for round_num in range(_MAX_TOOL_ROUNDS):
        logger.debug("LLM call round %d, %d messages", round_num + 1, len(llm_messages))

        response = await litellm.acompletion(
            model=settings.LLM_MODEL,
            messages=llm_messages,
            tools=TOOLS,
            tool_choice="auto",
            api_key=settings.LLM_API_KEY,
            temperature=0.3,
        )

        response_message = response.choices[0].message

        # If no tool calls, we have the final answer
        if not response_message.tool_calls:
            break

        # Append the assistant's message (with tool_calls) to loop history
        llm_messages.append(response_message.model_dump())

        # Execute each tool call
        for tool_call in response_message.tool_calls:
            fn_name = tool_call.function.name
            fn_args_str = tool_call.function.arguments

            logger.info("Tool call: %s(%s)", fn_name, fn_args_str)

            try:
                fn_args = json.loads(fn_args_str)
            except json.JSONDecodeError:
                fn_args = {}

            tool_fn = _TOOL_DISPATCH.get(fn_name)
            if tool_fn:
                result = await tool_fn(**fn_args)
                if fn_name == "get_alerts":
                    sources.extend(["sachet-ndma", "imd"])
                else:
                    sources.append("open-meteo")
            else:
                result = json.dumps({"error": f"Unknown tool: {fn_name}"})
                logger.warning("Unknown tool requested: %s", fn_name)

            # Append tool result to conversation loop
            llm_messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })
    else:
        # Exhausted max rounds — force a response without tools
        logger.warning("Hit max tool rounds (%d), forcing final response", _MAX_TOOL_ROUNDS)
        response = await litellm.acompletion(
            model=settings.LLM_MODEL,
            messages=llm_messages,
            api_key=settings.LLM_API_KEY,
            temperature=0.3,
        )
        response_message = response.choices[0].message

    reply = response_message.content or "I'm sorry, I couldn't generate a response. Please try again."

    # Update conversation history with user message and assistant reply
    new_history = list(history)
    new_history.append({"role": "user", "content": message})
    new_history.append({"role": "assistant", "content": reply})
    await _save_session_history(sid, new_history)

    # Deduplicate sources
    unique_sources = list(dict.fromkeys(sources))

    logger.info("Chat complete: session=%s, %d sources, reply length %d", sid, len(unique_sources), len(reply))

    return ChatResponse(
        reply=reply,
        language=language,
        session_id=sid,
        sources=unique_sources,
    )
