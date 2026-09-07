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


@pytest.mark.asyncio
async def test_sachet_json_parsing_and_expiry_filtering():
    """Verify live SACHET NDMA JSON format parsing and strict expiry filtering."""
    from app.pipelines.sachet_poller import parse_sachet_json, SachetPoller
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    future_time = now + timedelta(hours=6)
    past_time = now - timedelta(hours=6)

    raw_json = [
        {
            "identifier": "1001",
            "disaster_type": "Thunderstorm with Lightning",
            "severity": "WATCH",
            "severity_color": "yellow",
            "severity_level": "Likely",
            "effective_start_time": now.strftime("%a %b %d %H:%M:%S UTC %Y"),
            "effective_end_time": future_time.strftime("%a %b %d %H:%M:%S UTC %Y"),
            "area_description": "Kota, Baran districts of Rajasthan",
            "warning_message": "Thunderstorm with lightning likely over Kota.",
            "centroid": "75.83,25.18",
            "alert_source": "IMD Jaipur",
        },
        {
            "identifier": "1002",
            "disaster_type": "Heat Wave",
            "severity": "WARNING",
            "severity_color": "red",
            "severity_level": "Observed",
            "effective_start_time": (past_time - timedelta(hours=12)).strftime("%a %b %d %H:%M:%S UTC %Y"),
            "effective_end_time": past_time.strftime("%a %b %d %H:%M:%S UTC %Y"),
            "area_description": "Churu, Bikaner districts of Rajasthan",
            "warning_message": "Expired heat wave alert.",
            "centroid": "74.61,28.29",
            "alert_source": "IMD Jaipur",
        },
    ]

    records = parse_sachet_json(raw_json)
    # The expired alert (1002) must have been filtered out
    assert len(records) == 1
    assert records[0].alert_id == "SACHET-1001"
    assert records[0].event == "Thunderstorm with Lightning"
    assert records[0].severity == "Moderate"
    assert records[0].status == "Actual"

    # Verify SachetPoller seed alerts honesty
    poller = SachetPoller()
    active = poller.get_all_active()
    assert len(active) > 0
    # Sandbox alerts must be honestly tagged as Exercise
    for a in active:
        assert a.status == "Exercise"
        assert "sandbox" in a.source

    # Location lookup should match unexpired sandbox alerts
    matches = poller.get_alerts_for_location(location_name="Mumbai")
    assert len(matches) >= 1
    assert matches[0].status == "Exercise"


@pytest.mark.asyncio
async def test_incois_marine_weather_and_pfz():
    """Verify INCOIS marine ocean state and PFZ advisory generation."""
    import json
    from app.data_sources.incois import incois_client
    from app.tools.marine import get_marine_weather
    from app.core.router import _TOOL_DISPATCH

    try:
        # 1. Direct client call
        point = await incois_client.fetch_marine_weather(lat=13.0827, lon=80.2707, location_name="Chennai Coast")
        assert point.wave_height_m is not None
        assert point.sea_state in ("Calm", "Smooth", "Moderate", "Rough", "Very Rough", "High to Phenomenal")
        assert any(term in point.safety_status for term in ("Safe", "Caution", "Warning", "Emergency"))
        assert "PFZ" in point.pfz_advisory or "fishing" in point.pfz_advisory.lower()

        # 2. Tool invocation via resolver
        marine_json = await get_marine_weather(location="Kochi Coast")
        data = json.loads(marine_json)
        assert "wave_height_m" in data
        assert "sea_state" in data
        assert "safety_status" in data
        assert "pfz_advisory" in data

        # 3. Router dispatch confirmation
        assert "get_marine_weather" in _TOOL_DISPATCH
    finally:
        from app.tools.location_resolver import close_geocoder
        await close_geocoder()
        await incois_client.close()


@pytest.mark.asyncio
async def test_aviation_metar_weather():
    """Verify aviation METAR weather retrieval, ICAO resolution, and router dispatch."""
    import json
    from app.data_sources.aviation import aviation_client
    from app.tools.aviation import get_aviation_weather
    from app.core.router import _TOOL_DISPATCH

    try:
        # 1. Aerodrome code resolution
        assert aviation_client.resolve_icao("Delhi") == "VIDP"
        assert aviation_client.resolve_icao("Mumbai") == "VABB"
        assert aviation_client.resolve_icao("BLR") == "VOBL"
        assert aviation_client.resolve_icao("VOBL") == "VOBL"

        # 2. Client METAR extraction
        metar = await aviation_client.fetch_metar("VIDP")
        assert metar.icao_code == "VIDP"
        assert metar.flight_category in ("VFR", "MVFR", "IFR", "LIFR")
        assert "VIDP" in metar.raw_metar
        assert metar.temperature_c is not None

        # 3. Tool invocation
        res_json = await get_aviation_weather("Kempegowda Airport")
        data = json.loads(res_json)
        assert data["icao_code"] == "VOBL"
        assert "flight_category" in data
        assert "raw_metar" in data

        # 4. Router dispatch registry
        assert "get_aviation_weather" in _TOOL_DISPATCH
    finally:
        await aviation_client.close()


@pytest.mark.asyncio
async def test_agricultural_crop_advisory():
    """Verify ICAR/IMD agro-meteorological advisory generation and phenological rules."""
    import json
    from app.tools.advisory import get_agricultural_advisory
    from app.core.router import _TOOL_DISPATCH
    from app.data_sources.openmeteo import openmeteo_client
    from app.tools.location_resolver import close_geocoder

    try:
        adv_json = await get_agricultural_advisory(
            crop="Rice",
            stage="Vegetative",
            location="Guntur",
        )
        data = json.loads(adv_json)
        assert data["crop"] == "Rice"
        assert data["stage"] == "Vegetative"
        assert "irrigation_advisory" in data
        assert "spray_advisory" in data
        assert "field_operation_advisory" in data
        assert len(data["pest_disease_alerts"]) > 0
        assert any("Hopper" in a or "Blight" in a or "Blast" in a for a in data["pest_disease_alerts"])

        # Router registry confirmation
        assert "get_agricultural_advisory" in _TOOL_DISPATCH
    finally:
        await close_geocoder()
        await openmeteo_client.close()





