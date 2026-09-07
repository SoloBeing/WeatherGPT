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
from app.core.templates import (
    format_alerts,
    format_aviation_weather,
    format_crop_advisory,
    format_current_weather,
    format_forecast,
    format_marine_weather,
)
from app.database.redis_cache import cache
from app.models.schemas import (
    AlertListResponse,
    AviationWeather,
    ChatResponse,
    CropAdvisoryReport,
    ForecastPoint,
    ForecastTimeline,
    MarinePoint,
)
from app.tools.alerts_tool import get_alerts
from app.tools.current import get_current_weather
from app.tools.forecast import get_forecast
from app.tools.marine import get_marine_weather
from app.tools.aviation import get_aviation_weather
from app.tools.advisory import get_agricultural_advisory
from app.tools.climatology import get_climatology

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
5. When a user asks about marine weather, sea conditions, wave height, swell, ocean currents,
   sea surface temperature, or fishing / PFZ advisories for coastal regions, call `get_marine_weather`.
6. When a user asks about aviation weather, airport conditions, METAR reports, flight categories
   (VFR/IFR/LIFR), runway visibility, ceiling, or crosswinds for an aerodrome, call `get_aviation_weather`.
7. When a user asks about farming advice, crop advisories, agricultural weather, irrigation timing,
   pesticide/fertilizer spraying, sowing, or harvest precautions, call `get_agricultural_advisory`.
8. When a user asks about historical climate trends, multi-decadal normals (1991-2020), past rainfall/temperature baselines, standard deviation, anomalies, or climate change patterns, call `get_climatology`.
9. If a user refers to a location mentioned earlier in the conversation (e.g. "any alerts there?"),
   use that location in your tool call.
10. After receiving tool results, present the data conversationally and clearly:
   - For multi-day forecasts: summarize each day with date/day, conditions, min-max temps, and rain probability.
   - For disaster alerts: highlight the severity level (Red/Extreme, Orange/Severe, Yellow/Moderate), affected areas, and safety instructions clearly.
   - For marine reports: clearly state wave height, sea state, safety advisory for fishermen, and PFZ coordinates.
   - For aviation reports: clearly state flight category (VFR/MVFR/IFR), ceiling, visibility, wind speed/direction, and include the decoded METAR highlights.
   - For crop advisories: highlight irrigation guidance, spray precautions, harvest windows, and pest/disease alerts.
   - For climatology reports: highlight baseline normal, extreme min/max, standard deviation, decadal warming trend, and recent anomalies.
   - Always mention the data source (e.g. "According to NDMA SACHET / IMD...", "According to INCOIS...", "Per Aviation Weather Center METAR...", "According to ICAR / IMD Agromet...", "According to ECMWF ERA5 Reanalysis...", or "According to Open-Meteo...").
11. If a tool returns an error or no alerts found, inform the user honestly.
12. For greetings, chit-chat, or non-weather questions, respond naturally without calling tools.
13. If the user speaks in Hindi or another Indian language, respond in that language while keeping
   numbers and units in standard form.
13. Be concise, well-structured, and helpful. Use emoji sparingly to enhance readability (🚨 🌤️ 🌾 🌊 ✈️ ☀️ 🌧️ etc.).
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
    {
        "type": "function",
        "function": {
            "name": "get_marine_weather",
            "description": (
                "Get marine weather, wave height, swell, sea state, and INCOIS Potential Fishing "
                "Zone (PFZ) advisories for coastal regions, ports, and offshore waters."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": (
                            "Coastal city, port, or region name, e.g. 'Chennai', 'Kochi', 'Mumbai', "
                            "'Visakhapatnam', 'Goa', 'Puri'."
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
            "name": "get_aviation_weather",
            "description": (
                "Get official METAR aviation weather, flight category (VFR/MVFR/IFR), ceiling, "
                "visibility, crosswinds, and altimeter setting for an airport or aerodrome."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "airport": {
                        "type": "string",
                        "description": (
                            "Airport name, city, 4-letter ICAO code, or 3-letter IATA code, "
                            "e.g. 'VIDP', 'Delhi Airport', 'VABB', 'Mumbai', 'BLR', 'VOBL', 'Goa'."
                        ),
                    },
                },
                "required": ["airport"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_agricultural_advisory",
            "description": (
                "Get ICAR / IMD agro-meteorological farming advisory for a crop, growth stage, and location. "
                "Provides deterministic irrigation scheduling, pesticide spray timing, and harvesting advice."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "crop": {
                        "type": "string",
                        "description": "Crop name, e.g. 'Rice', 'Wheat', 'Cotton', 'Mustard', 'Sugarcane'.",
                    },
                    "stage": {
                        "type": "string",
                        "description": "Growth stage, e.g. 'Sowing', 'Vegetative', 'Flowering', 'Harvesting'.",
                    },
                    "location": {
                        "type": "string",
                        "description": "Farming district, taluk, or village name, e.g. 'Guntur', 'Karnal', 'Wardha'.",
                    },
                },
                "required": ["crop", "stage", "location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_climatology",
            "description": (
                "Retrieve historical climatological normals, anomalies, variability, and decadal trends "
                "from ECMWF ERA5 multi-decadal reanalysis for an Indian location."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City, district, or state name, e.g. 'Delhi', 'Bengaluru', 'Rajasthan'.",
                    },
                    "variable": {
                        "type": "string",
                        "description": "Target meteorological variable: 'temperature', 'precipitation', or 'all'.",
                    },
                    "start_year": {
                        "type": "integer",
                        "description": "Start year of baseline period (default: 1991 for standard WMO normal).",
                    },
                    "end_year": {
                        "type": "integer",
                        "description": "End year of baseline period (default: 2020 for standard WMO normal).",
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
    "get_marine_weather": get_marine_weather,
    "get_aviation_weather": get_aviation_weather,
    "get_agricultural_advisory": get_agricultural_advisory,
    "get_climatology": get_climatology,
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
    last_tool_data: Optional[dict] = None
    last_factual_template: Optional[str] = None

    try:
        # --- Tool-calling loop ---
        for _ in range(_MAX_TOOL_ROUNDS):
            response = await litellm.acompletion(
                model=settings.LLM_MODEL,
                messages=llm_messages,
                tools=TOOLS,
                tool_choice="auto",
                api_key=settings.LLM_API_KEY,
                temperature=0.2,
            )

            response_message = response.choices[0].message

            # If LLM didn't call a tool, we're done
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
                    parsed_res: dict = {}
                    try:
                        loaded = json.loads(result)
                        if isinstance(loaded, dict) and "error" not in loaded:
                            parsed_res = loaded
                            last_tool_data = parsed_res
                    except Exception:
                        parsed_res = {}

                    # Dynamic Source Attribution (Item #9)
                    tool_source = parsed_res.get("source") if isinstance(parsed_res, dict) else None
                    if tool_source:
                        sources.append(tool_source)
                    elif fn_name == "get_alerts":
                        sources.extend(["sachet-ndma", "imd"])
                    elif fn_name == "get_marine_weather":
                        sources.append("INCOIS / Open-Meteo Marine")
                    elif fn_name == "get_aviation_weather":
                        sources.append("NOAA Aviation Weather Center (METAR)")
                    elif fn_name == "get_agricultural_advisory":
                        sources.append("ICAR / IMD Agromet Engine")
                    elif fn_name == "get_climatology":
                        sources.append("ECMWF ERA5 Reanalysis")
                    else:
                        sources.append("open-meteo")

                    # Verified Factual Template Generation (Item #8 Anti-Hallucination)
                    factual_text: Optional[str] = None
                    try:
                        if fn_name == "get_current_weather" and parsed_res:
                            factual_text = format_current_weather(ForecastPoint.model_validate(parsed_res), language=language)
                        elif fn_name == "get_forecast" and parsed_res:
                            factual_text = format_forecast(ForecastTimeline.model_validate(parsed_res), language=language)
                        elif fn_name == "get_alerts" and parsed_res:
                            factual_text = format_alerts(AlertListResponse.model_validate(parsed_res), language=language)
                        elif fn_name == "get_marine_weather" and parsed_res:
                            factual_text = format_marine_weather(MarinePoint.model_validate(parsed_res))
                        elif fn_name == "get_aviation_weather" and parsed_res:
                            factual_text = format_aviation_weather(AviationWeather.model_validate(parsed_res))
                        elif fn_name == "get_agricultural_advisory" and parsed_res:
                            factual_text = format_crop_advisory(CropAdvisoryReport.model_validate(parsed_res))
                        elif fn_name == "get_climatology" and parsed_res:
                            factual_text = parsed_res.get("narrative_summary")
                    except Exception as exc:
                        logger.debug("Factual template generation skipped for %s: %s", fn_name, exc)

                    if factual_text:
                        last_factual_template = factual_text
                        tool_content = (
                            f"{result}\n\n"
                            f"[DETERMINISTIC FACTUAL SUMMARY — PRESERVE THESE VALUES AND CORE FACTS EXACTLY]:\n"
                            f"{factual_text}"
                        )
                    else:
                        tool_content = result
                else:
                    tool_content = json.dumps({"error": f"Unknown tool: {fn_name}"})
                    logger.warning("Unknown tool requested: %s", fn_name)

                # Append tool result to conversation loop
                llm_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_content,
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

        reply = response_message.content or last_factual_template or "I'm sorry, I couldn't generate a response. Please try again."
    except Exception as exc:
        logger.warning("LLM generation loop failed (%s); checking factual template fallback", exc)
        if last_factual_template:
            reply = last_factual_template
        else:
            raise

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
        data=last_tool_data,
        session_id=sid,
        sources=unique_sources,
    )

