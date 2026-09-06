"""
Bhashini Service Client — Govt-backed multilingual ASR + MT + TTS.

ULCA APIs supporting 22 Indian languages.
Used for: voice input (ASR), translation (MT), voice output (TTS).
Fallback: Groq Whisper for ASR, gTTS for TTS if Bhashini rate-limits.

Architecture (two-step):
  1. Pipeline Config Discovery — POST to ULCA config endpoint with static
     credentials (userID + ulcaApiKey) to get serviceIds + inference JWT.
  2. Pipeline Compute — POST to Dhruva inference endpoint with dynamic JWT
     to execute ASR / NMT / TTS.

The pipeline config is cached in-memory (~1 hour) to avoid redundant
discovery calls on every voice turn.
"""

import base64
import io
import logging
import time
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Language registry — 22 Scheduled Languages + English
# ---------------------------------------------------------------------------

SUPPORTED_LANGUAGES: dict[str, str] = {
    "en": "English",
    "hi": "Hindi",
    "ta": "Tamil",
    "te": "Telugu",
    "bn": "Bengali",
    "mr": "Marathi",
    "gu": "Gujarati",
    "kn": "Kannada",
    "ml": "Malayalam",
    "or": "Odia",
    "pa": "Punjabi",
    "as": "Assamese",
    "ur": "Urdu",
    "sa": "Sanskrit",
    "mai": "Maithili",
    "doi": "Dogri",
    "ks": "Kashmiri",
    "kok": "Konkani",
    "sd": "Sindhi",
    "ne": "Nepali",
    "sat": "Santali",
    "brx": "Bodo",
    "mni": "Manipuri",
}


class BhashiniError(Exception):
    """Raised when Bhashini API calls fail after retries."""
    pass


class BhashiniService:
    """Bhashini ULCA pipeline client for ASR, NMT, and TTS.

    Follows the same service-class + sandbox-fallback pattern as FCMService.
    If BHASHINI_API_KEY is empty, runs in sandbox mode (logs calls, returns mocks).
    """

    # Pipeline config cache TTL (seconds)
    _PIPELINE_CACHE_TTL = 3600  # 1 hour

    def __init__(self) -> None:
        self._api_key = settings.BHASHINI_API_KEY
        self._user_id = settings.BHASHINI_USER_ID
        self._config_url = settings.BHASHINI_ULCA_CONFIG_URL
        self._pipeline_id = settings.BHASHINI_PIPELINE_ID
        self._tts_gender = settings.BHASHINI_TTS_GENDER

        # Pipeline discovery cache
        self._inference_url: Optional[str] = None
        self._inference_auth_key: Optional[str] = "Authorization" if settings.BHASHINI_INFERENCE_KEY else None
        self._inference_auth_value: Optional[str] = settings.BHASHINI_INFERENCE_KEY or None
        self._service_ids: dict[str, str] = {}  # taskType → serviceId
        self._pipeline_cached_at: float = 0.0

        # HTTP client (shared, connection-pooled)
        self._client = httpx.AsyncClient(timeout=30.0)

        self._sandbox = not (self._api_key and self._user_id)
        if self._sandbox:
            logger.info("Bhashini credentials not configured. Running in SANDBOX mode.")
        else:
            logger.info("BhashiniService initialised (pipeline=%s).", self._pipeline_id)

    # ------------------------------------------------------------------
    # Pipeline discovery
    # ------------------------------------------------------------------

    async def _discover_pipeline(self) -> None:
        """Call ULCA config endpoint to discover serviceIds + inference auth.

        Caches the result in-memory for _PIPELINE_CACHE_TTL seconds.
        """
        payload = {
            "pipelineTasks": [
                {"taskType": "asr", "config": {"language": {"sourceLanguage": "hi"}}},
                {"taskType": "translation", "config": {"language": {"sourceLanguage": "hi", "targetLanguage": "en"}}},
                {"taskType": "tts", "config": {"language": {"sourceLanguage": "en"}}},
            ],
            "pipelineRequestConfig": {"pipelineId": self._pipeline_id},
        }

        headers = {
            "Content-Type": "application/json",
            "userID": self._user_id,
            "ulcaApiKey": self._api_key,
        }

        logger.info("Discovering Bhashini pipeline config...")
        resp = await self._client.post(self._config_url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        # Extract inference endpoint + auth
        endpoint_info = data.get("pipelineInferenceAPIEndPoint", {})
        self._inference_url = endpoint_info.get("callbackUrl", "")
        auth_info = endpoint_info.get("inferenceApiKey", {})
        self._inference_auth_key = auth_info.get("name", "Authorization") or "Authorization"
        self._inference_auth_value = auth_info.get("value") or settings.BHASHINI_INFERENCE_KEY

        # Extract serviceIds for each task type
        for task_config in data.get("pipelineResponseConfig", []):
            task_type = task_config.get("taskType", "")
            configs = task_config.get("config", [])
            if configs and isinstance(configs, list):
                self._service_ids[task_type] = configs[0].get("serviceId", "")
            elif isinstance(configs, dict):
                self._service_ids[task_type] = configs.get("serviceId", "")

        self._pipeline_cached_at = time.time()
        logger.info(
            "Pipeline discovered: inference_url=%s, services=%s",
            self._inference_url,
            self._service_ids,
        )

    async def _ensure_pipeline(self) -> None:
        """Lazy-init: discover pipeline if not cached or expired."""
        if self._sandbox:
            return

        age = time.time() - self._pipeline_cached_at
        if not self._inference_url or age > self._PIPELINE_CACHE_TTL:
            await self._discover_pipeline()

    def _inference_headers(self) -> dict[str, str]:
        """Build headers for inference calls."""
        return {
            "Content-Type": "application/json",
            self._inference_auth_key or "Authorization": self._inference_auth_value or "",
        }

    # ------------------------------------------------------------------
    # ASR — Speech to Text
    # ------------------------------------------------------------------

    async def asr(
        self,
        audio_bytes: bytes,
        source_lang: str = "hi",
        audio_format: str = "wav",
        sampling_rate: int = 16000,
    ) -> str:
        """Transcribe audio to text using Bhashini ASR.

        Args:
            audio_bytes: Raw audio file bytes.
            source_lang: ISO 639-1 language code of the speech.
            audio_format: Audio format (wav, mp3, flac).
            sampling_rate: Audio sampling rate in Hz.

        Returns:
            Transcribed text string.

        Raises:
            BhashiniError: If both Bhashini and fallback fail.
        """
        if self._sandbox:
            logger.info("[Bhashini Sandbox] ASR called: lang=%s, %d bytes", source_lang, len(audio_bytes))
            return f"[sandbox-asr] Received {len(audio_bytes)} bytes of {source_lang} audio"

        await self._ensure_pipeline()

        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        service_id = self._service_ids.get("asr", "")

        payload = {
            "pipelineTasks": [
                {
                    "taskType": "asr",
                    "config": {
                        "language": {"sourceLanguage": source_lang},
                        "serviceId": service_id,
                        "audioFormat": audio_format,
                        "samplingRate": sampling_rate,
                    },
                }
            ],
            "inputData": {
                "audio": [{"audioContent": audio_b64}]
            },
        }

        try:
            resp = await self._client.post(
                self._inference_url, json=payload, headers=self._inference_headers()
            )

            # Retry once on 401 (expired inference token)
            if resp.status_code == 401:
                logger.warning("Bhashini ASR got 401 — rediscovering pipeline...")
                await self._discover_pipeline()
                resp = await self._client.post(
                    self._inference_url, json=payload, headers=self._inference_headers()
                )

            resp.raise_for_status()
            data = resp.json()

            transcript = (
                data.get("pipelineResponse", [{}])[0]
                .get("output", [{}])[0]
                .get("source", "")
            )
            logger.info("Bhashini ASR success: lang=%s, transcript=%d chars", source_lang, len(transcript))
            return transcript

        except Exception as e:
            logger.error("Bhashini ASR failed: %s — trying Groq Whisper fallback", e)
            return await self._groq_whisper_fallback(audio_bytes, source_lang)

    async def _groq_whisper_fallback(self, audio_bytes: bytes, source_lang: str) -> str:
        """Fallback ASR using Groq's Whisper API.

        Uses the same LLM_API_KEY (Groq key) already configured.
        """
        try:
            import litellm

            logger.info("Attempting Groq Whisper fallback ASR (lang=%s)...", source_lang)

            response = await litellm.atranscription(
                model=f"groq/{settings.GROQ_WHISPER_MODEL}",
                file=("audio.wav", audio_bytes),
                api_key=settings.LLM_API_KEY,
                language=source_lang,
            )
            transcript = response.text or ""
            logger.info("Groq Whisper fallback success: %d chars", len(transcript))
            return transcript

        except Exception as e2:
            logger.error("Groq Whisper fallback also failed: %s", e2)
            raise BhashiniError(f"All ASR methods failed. Bhashini + Groq Whisper: {e2}") from e2

    # ------------------------------------------------------------------
    # NMT — Translation
    # ------------------------------------------------------------------

    async def translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
    ) -> str:
        """Translate text between Indian languages using Bhashini NMT.

        Args:
            text: Source text to translate.
            source_lang: ISO 639-1 source language code.
            target_lang: ISO 639-1 target language code.

        Returns:
            Translated text string.
        """
        if source_lang == target_lang:
            return text

        if self._sandbox:
            logger.info("[Bhashini Sandbox] NMT: %s→%s, text=%s", source_lang, target_lang, text[:80])
            return text  # Pass-through in sandbox

        await self._ensure_pipeline()

        service_id = self._service_ids.get("translation", "")

        payload = {
            "pipelineTasks": [
                {
                    "taskType": "translation",
                    "config": {
                        "language": {
                            "sourceLanguage": source_lang,
                            "targetLanguage": target_lang,
                        },
                        "serviceId": service_id,
                    },
                }
            ],
            "inputData": {
                "input": [{"source": text}]
            },
        }

        try:
            resp = await self._client.post(
                self._inference_url, json=payload, headers=self._inference_headers()
            )

            if resp.status_code == 401:
                logger.warning("Bhashini NMT got 401 — rediscovering pipeline...")
                await self._discover_pipeline()
                resp = await self._client.post(
                    self._inference_url, json=payload, headers=self._inference_headers()
                )

            resp.raise_for_status()
            data = resp.json()

            translated = (
                data.get("pipelineResponse", [{}])[0]
                .get("output", [{}])[0]
                .get("target", text)
            )
            logger.info("Bhashini NMT success: %s→%s, %d→%d chars", source_lang, target_lang, len(text), len(translated))
            return translated

        except Exception as e:
            logger.error("Bhashini NMT failed (%s→%s): %s — returning original text", source_lang, target_lang, e)
            return text  # Graceful degradation: return original

    # ------------------------------------------------------------------
    # TTS — Text to Speech
    # ------------------------------------------------------------------

    async def tts(
        self,
        text: str,
        target_lang: str = "hi",
        gender: Optional[str] = None,
    ) -> bytes:
        """Synthesise speech from text using Bhashini TTS.

        Args:
            text: Text to synthesise.
            target_lang: ISO 639-1 language code for voice output.
            gender: Voice gender ('male' or 'female'). Defaults to config.

        Returns:
            WAV audio bytes.

        Raises:
            BhashiniError: If both Bhashini and gTTS fallback fail.
        """
        if self._sandbox:
            logger.info("[Bhashini Sandbox] TTS called: lang=%s, text=%s", target_lang, text[:80])
            return b""  # Empty bytes in sandbox

        await self._ensure_pipeline()

        service_id = self._service_ids.get("tts", "")
        voice_gender = gender or self._tts_gender

        payload = {
            "pipelineTasks": [
                {
                    "taskType": "tts",
                    "config": {
                        "language": {"sourceLanguage": target_lang},
                        "serviceId": service_id,
                        "gender": voice_gender,
                    },
                }
            ],
            "inputData": {
                "input": [{"source": text}]
            },
        }

        try:
            resp = await self._client.post(
                self._inference_url, json=payload, headers=self._inference_headers()
            )

            if resp.status_code == 401:
                logger.warning("Bhashini TTS got 401 — rediscovering pipeline...")
                await self._discover_pipeline()
                resp = await self._client.post(
                    self._inference_url, json=payload, headers=self._inference_headers()
                )

            resp.raise_for_status()
            data = resp.json()

            audio_b64 = (
                data.get("pipelineResponse", [{}])[0]
                .get("audio", [{}])[0]
                .get("audioContent", "")
            )

            audio_bytes = base64.b64decode(audio_b64)
            logger.info("Bhashini TTS success: lang=%s, %d audio bytes", target_lang, len(audio_bytes))
            return audio_bytes

        except Exception as e:
            logger.error("Bhashini TTS failed: %s — trying gTTS fallback", e)
            return await self._gtts_fallback(text, target_lang)

    async def _gtts_fallback(self, text: str, target_lang: str) -> bytes:
        """Fallback TTS using Google Translate TTS (gTTS).

        Generates MP3, converts conceptually to bytes for the response.
        """
        try:
            from gtts import gTTS

            # gTTS uses slightly different lang codes; map common ones
            gtts_lang = target_lang if target_lang != "or" else "or"

            logger.info("Attempting gTTS fallback (lang=%s)...", gtts_lang)
            tts_obj = gTTS(text=text, lang=gtts_lang, slow=False)

            buf = io.BytesIO()
            tts_obj.write_to_fp(buf)
            buf.seek(0)
            audio_bytes = buf.read()

            logger.info("gTTS fallback success: %d bytes", len(audio_bytes))
            return audio_bytes

        except Exception as e2:
            logger.error("gTTS fallback also failed: %s", e2)
            raise BhashiniError(f"All TTS methods failed. Bhashini + gTTS: {e2}") from e2

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()


# ---------------------------------------------------------------------------
# Shared singleton instance
# ---------------------------------------------------------------------------

bhashini_service = BhashiniService()
"""Module-level singleton — import this from routes and orchestrator."""
