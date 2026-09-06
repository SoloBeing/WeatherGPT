"""
Voice Chat Route — Audio-in, audio-out weather assistant.

Full pipeline:
  Audio upload → Bhashini ASR → (NMT if needed) → LLM orchestrator
  → weather tools → (NMT reply if needed) → Bhashini TTS → Audio out

Hindi goes directly to the LLM (system prompt handles Hindi natively).
Other Indic languages get an NMT round-trip (Indic→English→Indic).
"""

import base64
import logging
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.services.bhashini import SUPPORTED_LANGUAGES, bhashini_service
from app.llm_orchestrator.router import chat
from app.models.schemas import VoiceChatResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])

# Maximum upload size (10 MB)
_MAX_AUDIO_BYTES = 10 * 1024 * 1024

# Allowed audio extensions
_ALLOWED_EXTENSIONS = {"wav", "mp3", "flac", "ogg", "m4a", "webm", "aac"}

# Languages the LLM system prompt handles natively (no NMT needed before LLM)
_LLM_NATIVE_LANGS = {"en", "hi"}


@router.post("/chat", response_model=VoiceChatResponse)
async def voice_chat_endpoint(
    audio: UploadFile = File(..., description="Audio file (WAV/MP3/FLAC, max 10MB)"),
    language: str = Form(default="hi", description="ISO 639-1 source language code"),
    session_id: Optional[str] = Form(default=None, description="Session ID for conversation continuity"),
    response_format: str = Form(default="audio", description="'audio' for TTS response, 'text' for text-only"),
) -> VoiceChatResponse:
    """Process a voice weather query through the full ASR → LLM → TTS pipeline.

    Accepts an audio file upload with language metadata, transcribes it,
    routes through the LLM orchestrator (which calls weather tools),
    and returns both text and synthesised audio response.

    Example:
        POST /voice/chat
        Content-Type: multipart/form-data
        - audio: hindi_weather_query.wav
        - language: hi

        → {"transcript_in": "दिल्ली में मौसम कैसा है?",
           "reply_text": "दिल्ली में अभी: 34°C ...",
           "reply_audio_base64": "UklGRi4A...",
           "language": "hi", ...}
    """
    # ── 1. Validate ──────────────────────────────────────────────────
    if language not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported language '{language}'. Supported: {list(SUPPORTED_LANGUAGES.keys())}",
        )

    # Check file extension
    filename = audio.filename or "audio.wav"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio format '.{ext}'. Allowed: {_ALLOWED_EXTENSIONS}",
        )

    try:
        # Read audio bytes with size check
        audio_bytes = await audio.read()
        if len(audio_bytes) > _MAX_AUDIO_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Audio file too large ({len(audio_bytes)} bytes). Max: {_MAX_AUDIO_BYTES} bytes (10MB).",
            )

        if len(audio_bytes) == 0:
            raise HTTPException(status_code=400, detail="Empty audio file.")

        logger.info(
            "Voice chat request: lang=%s, format=%s, audio=%d bytes, session=%s",
            language, ext, len(audio_bytes), session_id,
        )

        # ── 2. ASR — Speech to Text ──────────────────────────────────────
        try:
            transcript = await bhashini_service.asr(
                audio_bytes=audio_bytes,
                source_lang=language,
                audio_format=ext if ext in {"wav", "mp3", "flac"} else "wav",
            )
        except Exception as e:
            logger.exception("ASR failed: %s", e)
            raise HTTPException(status_code=502, detail=f"Speech recognition failed: {e}") from e

        if not transcript.strip():
            raise HTTPException(status_code=422, detail="Could not recognise any speech in the audio.")

        logger.info("ASR transcript (%s): %s", language, transcript[:100])

        # ── 3. Translate to LLM-native language if needed ────────────────
        llm_input_text = transcript
        if language not in _LLM_NATIVE_LANGS:
            try:
                llm_input_text = await bhashini_service.translate(
                    text=transcript,
                    source_lang=language,
                    target_lang="en",
                )
                logger.info("NMT %s→en: %s", language, llm_input_text[:100])
            except Exception as e:
                logger.warning("NMT %s→en failed: %s — sending original to LLM", language, e)
                # Graceful degradation: send original text, LLM may still understand

        # ── 4. LLM Orchestrator — intent + tools + response ──────────────
        try:
            chat_response = await chat(
                message=llm_input_text,
                language=language,
                session_id=session_id,
            )
        except Exception as e:
            logger.exception("Chat processing failed: %s", e)
            raise HTTPException(status_code=500, detail=f"Failed to process query: {e}") from e

        reply_text = chat_response.reply

        # ── 5. Translate reply to user's language if needed ───────────────
        if language not in _LLM_NATIVE_LANGS:
            try:
                reply_text = await bhashini_service.translate(
                    text=chat_response.reply,
                    source_lang="en",
                    target_lang=language,
                )
                logger.info("NMT en→%s: %s", language, reply_text[:100])
            except Exception as e:
                logger.warning("NMT en→%s failed: %s — returning English reply", language, e)
                # Graceful degradation: return English reply text

        # ── 6. TTS — Text to Speech (if requested) ───────────────────────
        reply_audio_b64: Optional[str] = None
        if response_format == "audio":
            try:
                audio_out = await bhashini_service.tts(
                    text=reply_text,
                    target_lang=language,
                )
                if audio_out:
                    reply_audio_b64 = base64.b64encode(audio_out).decode("utf-8")
                    logger.info("TTS output: %d audio bytes for lang=%s", len(audio_out), language)
            except Exception as e:
                logger.warning("TTS failed: %s — returning text-only response", e)
                # Graceful degradation: return text without audio

        logger.info(
            "Voice chat complete: session=%s, transcript=%d chars, reply=%d chars, has_audio=%s",
            chat_response.session_id, len(transcript), len(reply_text), reply_audio_b64 is not None,
        )

        return VoiceChatResponse(
            transcript_in=transcript,
            reply_text=reply_text,
            reply_audio_base64=reply_audio_b64,
            language=language,
            session_id=chat_response.session_id,
            sources=chat_response.sources,
        )
    finally:
        await audio.close()


@router.get("/languages")
async def list_supported_languages():
    """Return the list of supported voice languages."""
    return {
        "languages": [
            {"code": code, "name": name}
            for code, name in SUPPORTED_LANGUAGES.items()
        ],
        "count": len(SUPPORTED_LANGUAGES),
    }
