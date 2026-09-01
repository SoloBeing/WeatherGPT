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

import litellm

from app.config import settings
from app.schemas_and_models.schemas import ChatResponse
from app.weather_tools.current import get_current_weather

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt — enforces the "LLM never computes weather" boundary
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are WeatherGPT, a helpful and friendly weather assistant specialising in India.

## RULES — read these carefully:
1. You NEVER make up, estimate, or recall weather data from memory.
   Every weather number MUST come from a tool call.
2. When a user asks about current weather, forecasts, or conditions for
   ANY location, you MUST call the appropriate tool first.
3. After receiving tool results, present the data conversationally.
   Always mention the data source (e.g. "According to Open-Meteo...").
4. If a tool returns an error, tell the user honestly and suggest
   alternatives (e.g. try a different city name).
5. For greetings, chit-chat, or non-weather questions, respond naturally
   without calling tools.
6. When presenting weather data:
   - Lead with the most important info (temperature, conditions)
   - Include feels-like temperature if significantly different
   - Mention wind, humidity, and pressure when relevant
   - Use emoji sparingly to enhance readability (🌤️ ☀️ 🌧️ etc.)
7. If the user speaks in Hindi or another Indian language, respond in
   that language while keeping numbers and units in standard form.
8. Be concise. Don't repeat the same information.
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
                "temperature, or conditions in a city or place."
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
]

# Map tool names → async callables
_TOOL_DISPATCH: dict = {
    "get_current_weather": get_current_weather,
}

# Maximum tool-calling rounds to prevent infinite loops
_MAX_TOOL_ROUNDS = 5


async def chat(message: str, language: str = "en") -> ChatResponse:
    """Process a user message through the LLM orchestrator.

    Flow:
        1. Send user message + system prompt + tool definitions to LLM
        2. If LLM wants to call tools → execute them → feed results back
        3. LLM phrases the final response in natural language
        4. Return ChatResponse

    Args:
        message: The user's text message.
        language: ISO 639-1 language code.

    Returns:
        ChatResponse with the LLM's natural-language reply.
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": message},
    ]

    sources: list[str] = []

    # --- Tool-calling loop ---
    for round_num in range(_MAX_TOOL_ROUNDS):
        logger.debug("LLM call round %d, %d messages", round_num + 1, len(messages))

        response = await litellm.acompletion(
            model=settings.LLM_MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            api_key=settings.LLM_API_KEY,
            temperature=0.3,
        )

        response_message = response.choices[0].message

        # If no tool calls, we have the final answer
        if not response_message.tool_calls:
            break

        # Append the assistant's message (with tool_calls) to history
        messages.append(response_message.model_dump())

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
                sources.append("open-meteo")
            else:
                result = json.dumps({"error": f"Unknown tool: {fn_name}"})
                logger.warning("Unknown tool requested: %s", fn_name)

            # Append tool result to conversation
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })
    else:
        # Exhausted max rounds — force a response without tools
        logger.warning("Hit max tool rounds (%d), forcing final response", _MAX_TOOL_ROUNDS)
        response = await litellm.acompletion(
            model=settings.LLM_MODEL,
            messages=messages,
            api_key=settings.LLM_API_KEY,
            temperature=0.3,
        )
        response_message = response.choices[0].message

    reply = response_message.content or "I'm sorry, I couldn't generate a response. Please try again."

    # Deduplicate sources
    unique_sources = list(dict.fromkeys(sources))

    logger.info("Chat complete: %d sources, reply length %d", len(unique_sources), len(reply))

    return ChatResponse(
        reply=reply,
        language=language,
        sources=unique_sources,
    )
