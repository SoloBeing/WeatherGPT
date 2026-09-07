"""
Chat Route — Primary conversational endpoint.

Accepts text (or transcribed voice) → intent classifier → tool dispatch → phrased response.
This is the main request path from the spec:
  Voice/text → Bhashini ASR → intent classifier → tool layer → big model phrasing → Bhashini TTS
"""

import logging

from fastapi import APIRouter, HTTPException

from app.core.router import chat
from app.models.schemas import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest) -> ChatResponse:
    """Process a conversational weather query.

    Accepts a text message, routes it through the LLM orchestrator
    (which calls weather tools as needed), and returns a natural
    language response with real data.

    Example:
        POST /chat
        {"message": "What's the weather in Delhi?"}

        → {"reply": "Currently in Delhi: 34°C, partly cloudy...", ...}
    """
    logger.info(
        "Chat request: '%s' (lang=%s, session_id=%s)",
        request.message,
        request.language,
        request.session_id,
    )

    try:
        response = await chat(
            message=request.message,
            language=request.language,
            session_id=request.session_id,
        )
    except Exception as e:
        logger.exception("Chat processing failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred while processing your weather request. Please try again later.",
        ) from e

    logger.info("Chat response: %d chars, sources=%s", len(response.reply), response.sources)
    return response
