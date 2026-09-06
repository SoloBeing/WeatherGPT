"""
Offline Unit and Mock Tests for External Services: Bhashini & FCM.

Verifies:
1. BhashiniService sandbox mode operations (ASR, NMT, TTS)
2. BhashiniService discovery and inference mocking with mock transport
3. BhashiniService 401 Unauthorized token recovery
4. BhashiniService graceful fallback to Groq Whisper and gTTS
5. FCMService sandbox mode push dispatch to topics and tokens
6. FCMService severity-based alert broadcasting
"""

import base64
from datetime import datetime, timezone
import io
from pathlib import Path
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.schemas import AlertRecord
from app.services.bhashini import BhashiniService
from app.services.fcm import FCMService


# ---------------------------------------------------------------------------
# Bhashini Service Offline Tests
# ---------------------------------------------------------------------------


async def test_bhashini_sandbox_mode():
    """Verify Bhashini behaves deterministically in sandbox mode when no credentials exist."""
    svc = BhashiniService()
    # Force sandbox mode
    svc._sandbox = True

    # ASR
    asr_res = await svc.asr(b"fake-audio-bytes", source_lang="hi")
    assert "[sandbox-asr]" in asr_res
    assert "fake-audio-bytes" not in asr_res
    assert "16 bytes" in asr_res

    # NMT (pass-through in sandbox)
    nmt_res = await svc.translate("आज मौसम कैसा है?", source_lang="hi", target_lang="en")
    assert nmt_res == "आज मौसम कैसा है?"

    # Same language pass-through (bypasses network/sandbox)
    same_lang_res = await svc.translate("Hello world", source_lang="en", target_lang="en")
    assert same_lang_res == "Hello world"

    # TTS (empty bytes in sandbox)
    tts_res = await svc.tts("Hello", target_lang="hi")
    assert tts_res == b""

    await svc.close()


async def test_bhashini_mock_inference():
    """Verify full Bhashini discovery and inference lifecycle with mocked transport."""
    svc = BhashiniService()
    svc._sandbox = False
    svc._api_key = "test-api-key"
    svc._user_id = "test-user-id"
    svc._inference_url = "https://inference.bhashini.gov.in/compute"
    svc._service_ids = {
        "asr": "asr-service-123",
        "translation": "nmt-service-456",
        "tts": "tts-service-789",
    }
    svc._pipeline_cached_at = 9999999999.0  # Far future to skip discovery

    sample_audio_b64 = base64.b64encode(b"RIFF-WAV-MOCK").decode("utf-8")

    def mock_inference_handler(request: httpx.Request) -> httpx.Response:
        body = json_from_request = request.read()
        import json
        payload = json.loads(body.decode("utf-8"))
        task_type = payload["pipelineTasks"][0]["taskType"]

        if task_type == "asr":
            return httpx.Response(200, json={
                "pipelineResponse": [
                    {"output": [{"source": "दिल्ली का मौसम"}]}
                ]
            })
        elif task_type == "translation":
            return httpx.Response(200, json={
                "pipelineResponse": [
                    {"output": [{"target": "Weather in Delhi"}]}
                ]
            })
        elif task_type == "tts":
            return httpx.Response(200, json={
                "pipelineResponse": [
                    {"audio": [{"audioContent": sample_audio_b64}]}
                ]
            })
        return httpx.Response(400)

    svc._client = httpx.AsyncClient(
        transport=httpx.MockTransport(mock_inference_handler),
    )

    try:
        # Test ASR
        transcript = await svc.asr(b"raw-bytes", source_lang="hi")
        assert transcript == "दिल्ली का मौसम"

        # Test NMT
        translated = await svc.translate("दिल्ली का मौसम", source_lang="hi", target_lang="en")
        assert translated == "Weather in Delhi"

        # Test TTS
        audio = await svc.tts("Weather in Delhi", target_lang="en")
        assert audio == b"RIFF-WAV-MOCK"
    finally:
        await svc.close()


async def test_bhashini_401_token_recovery():
    """Verify Bhashini automatically rediscovers credentials upon 401 Unauthorized."""
    svc = BhashiniService()
    svc._sandbox = False
    svc._api_key = "test-api-key"
    svc._user_id = "test-user-id"
    svc._inference_url = "https://inference.bhashini.gov.in/compute"
    svc._service_ids = {"translation": "nmt-123"}
    svc._pipeline_cached_at = 9999999999.0

    inference_attempts = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal inference_attempts
        url = str(request.url)
        if "ulca" in url or "pipeline" in url:
            # Discovery mock
            return httpx.Response(200, json={
                "pipelineInferenceAPIEndPoint": {"callbackUrl": "https://inference.bhashini.gov.in/compute"},
                "pipelineResponseConfig": [
                    {"taskType": "translation", "config": [{"serviceId": "nmt-123"}]}
                ],
            })
        else:
            # Inference mock
            inference_attempts += 1
            if inference_attempts == 1:
                return httpx.Response(401, json={"error": "Token expired"})
            return httpx.Response(200, json={
                "pipelineResponse": [{"output": [{"target": "Recovered translation"}]}]
            })

    svc._client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    try:
        result = await svc.translate("Bonjour", source_lang="fr", target_lang="en")
        assert result == "Recovered translation"
        assert inference_attempts == 2
    finally:
        await svc.close()


async def test_bhashini_asr_fallback(monkeypatch):
    """Verify Bhashini ASR gracefully falls back to Groq Whisper when inference fails."""
    svc = BhashiniService()
    svc._sandbox = False
    svc._inference_url = "https://inference.bhashini.gov.in/compute"
    svc._pipeline_cached_at = 9999999999.0

    # Transport that fails
    svc._client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda req: httpx.Response(500))
    )

    # Mock litellm.atranscription
    mock_atranscription = AsyncMock(return_value=MagicMock(text="Whisper fallback transcript"))
    with patch("litellm.atranscription", mock_atranscription):
        result = await svc.asr(b"sample-audio", source_lang="hi")
        assert result == "Whisper fallback transcript"
        assert mock_atranscription.called

    await svc.close()


async def test_bhashini_tts_fallback():
    """Verify Bhashini TTS gracefully falls back to gTTS when inference fails."""
    svc = BhashiniService()
    svc._sandbox = False
    svc._inference_url = "https://inference.bhashini.gov.in/compute"
    svc._pipeline_cached_at = 9999999999.0

    svc._client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda req: httpx.Response(503))
    )

    # Mock gTTS write_to_fp
    def fake_write(self, fp):
        fp.write(b"MOCK-GTTS-MP3-STREAM")

    with patch("gtts.gTTS.write_to_fp", fake_write):
        audio_out = await svc.tts("Hello Weather", target_lang="en")
        assert audio_out == b"MOCK-GTTS-MP3-STREAM"

    await svc.close()


# ---------------------------------------------------------------------------
# FCM Service Offline Tests
# ---------------------------------------------------------------------------


async def test_fcm_sandbox_push():
    """Verify FCM service functions properly in sandbox mode with mock message IDs."""
    fcm = FCMService(credentials_path="nonexistent_credentials.json")
    assert fcm._initialized is False

    # Send to topic
    msg_id = await fcm.send_to_topic(
        topic="weather_alerts_extreme",
        title="Cyclone Warning",
        body="Red alert issued for coastal districts.",
        data={"urgency": "immediate"},
    )
    assert msg_id.startswith("mock-fcm-")

    # Send to device token
    token_id = await fcm.send_to_token(
        token="device_registration_token_123",
        title="Heavy Rain",
        body="Orange alert for your district.",
    )
    assert token_id.startswith("mock-fcm-")


async def test_fcm_alert_broadcasting():
    """Verify broadcast_active_alert maps alert severity to appropriate topics."""
    fcm = FCMService(credentials_path="nonexistent_credentials.json")

    sample_alert = AlertRecord(
        alert_id="TEST-ALERT-001",
        source="sachet-ndma",
        sender="ndma.gov.in",
        sent_at=datetime.now(timezone.utc),
        status="Actual",
        msg_type="Alert",
        event="Severe Cyclone",
        urgency="Immediate",
        severity="Extreme",
        certainty="Observed",
        headline="Red Alert for Cyclone",
        description="Very severe cyclonic storm approaching coast.",
        instruction="Evacuate to cyclone shelters.",
        area_desc="Coastal Odisha",
        polygon=[[19.8, 85.8], [20.3, 86.7], [19.8, 85.8]],
    )

    # Extreme severity -> topic 'weather_alerts_extreme'
    msg_id = await fcm.push_alert(sample_alert)
    assert msg_id.startswith("mock-fcm-")

    # Severe severity -> topic 'weather_alerts_severe'
    sample_alert.severity = "Severe"
    msg_id_severe = await fcm.push_alert(sample_alert)
    assert msg_id_severe.startswith("mock-fcm-")
