"""
Tests for Resilience Utilities, Open-Meteo Client, and Location Resolver.

Verifies:
1. Error classification (transient vs non-retryable status codes and network errors)
2. Jittered exponential backoff retry mechanics
3. Open-Meteo client fetch_current and fetch_forecast with offline mock transport
4. Open-Meteo transient error recovery (HTTP 429 / 503 retries)
5. Location resolver gazetteer fast-path, mocked geocoding, and offline fallback
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.resilience import (
    classify_http_error,
    is_retryable_http_error,
    retry_async,
)
from app.data_sources.openmeteo import OpenMeteoClient
from app.tools.location_resolver import resolve_location


# ---------------------------------------------------------------------------
# Resilience & Error Classification Tests
# ---------------------------------------------------------------------------


def test_error_classification():
    """Verify classification of transient vs non-retryable errors."""
    req = httpx.Request("GET", "https://api.example.com/test")

    # Timeouts & transport errors
    t_exc = httpx.ConnectTimeout("Connection timed out", request=req)
    assert is_retryable_http_error(t_exc) is True
    assert "timeout" in classify_http_error(t_exc).lower()

    net_exc = httpx.ConnectError("Connection refused", request=req)
    assert is_retryable_http_error(net_exc) is True
    assert "transport" in classify_http_error(net_exc).lower()

    # Retryable HTTP status codes
    for code in [429, 500, 502, 503, 504]:
        resp = httpx.Response(code, request=req)
        status_exc = httpx.HTTPStatusError("Transient error", request=req, response=resp)
        assert is_retryable_http_error(status_exc) is True, f"Code {code} should be retryable"

    # Non-retryable HTTP status codes
    for code in [400, 401, 403, 404, 422]:
        resp = httpx.Response(code, request=req)
        status_exc = httpx.HTTPStatusError("Client error", request=req, response=resp)
        assert is_retryable_http_error(status_exc) is False, f"Code {code} should not be retryable"
        assert "non-retryable" in classify_http_error(status_exc).lower()

    # Generic exceptions
    assert is_retryable_http_error(ValueError("bad value")) is False


async def test_retry_async_transient_recovery():
    """Verify retry_async recovers after transient failures with backoff."""
    call_count = 0
    req = httpx.Request("GET", "https://api.example.com/data")

    async def flaky_op():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            resp = httpx.Response(429, request=req)
            raise httpx.HTTPStatusError("Rate limited", request=req, response=resp)
        return {"status": "success", "attempts": call_count}

    result = await retry_async(
        flaky_op,
        max_retries=3,
        base_delay=0.01,
        max_delay=0.05,
        operation_name="flaky_op_test",
    )
    assert result["status"] == "success"
    assert call_count == 3


async def test_retry_async_non_retryable_fails_fast():
    """Verify non-retryable errors fail immediately on attempt 1."""
    call_count = 0
    req = httpx.Request("GET", "https://api.example.com/missing")

    async def not_found_op():
        nonlocal call_count
        call_count += 1
        resp = httpx.Response(404, request=req)
        raise httpx.HTTPStatusError("Not found", request=req, response=resp)

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await retry_async(
            not_found_op,
            max_retries=3,
            base_delay=0.01,
            operation_name="not_found_test",
        )
    assert exc_info.value.response.status_code == 404
    assert call_count == 1


async def test_retry_async_exhaustion():
    """Verify exception is raised when all retries are exhausted."""
    call_count = 0
    req = httpx.Request("GET", "https://api.example.com/service")

    async def failing_op():
        nonlocal call_count
        call_count += 1
        resp = httpx.Response(503, request=req)
        raise httpx.HTTPStatusError("Unavailable", request=req, response=resp)

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await retry_async(
            failing_op,
            max_retries=2,
            base_delay=0.01,
            operation_name="exhaustion_test",
        )
    assert exc_info.value.response.status_code == 503
    assert call_count == 3  # 1 initial + 2 retries


# ---------------------------------------------------------------------------
# Open-Meteo Offline Mock Tests
# ---------------------------------------------------------------------------

SAMPLE_OPENMETEO_CURRENT_RESPONSE = {
    "latitude": 28.625,
    "longitude": 77.25,
    "timezone": "Asia/Kolkata",
    "current": {
        "time": "2026-09-06T12:00",
        "temperature_2m": 31.5,
        "relative_humidity_2m": 68.0,
        "apparent_temperature": 36.2,
        "is_day": 1,
        "precipitation": 0.0,
        "rain": 0.0,
        "snowfall": 0.0,
        "weather_code": 1,
        "cloud_cover": 25.0,
        "pressure_msl": 1008.2,
        "surface_pressure": 985.0,
        "wind_speed_10m": 12.4,
        "wind_direction_10m": 110.0,
        "wind_gusts_10m": 18.2,
    },
}

SAMPLE_OPENMETEO_FORECAST_RESPONSE = {
    "latitude": 28.625,
    "longitude": 77.25,
    "timezone": "Asia/Kolkata",
    "daily": {
        "time": ["2026-09-06", "2026-09-07"],
        "weather_code": [1, 61],
        "temperature_2m_max": [34.0, 31.0],
        "temperature_2m_min": [25.0, 24.0],
        "apparent_temperature_max": [38.0, 35.0],
        "apparent_temperature_min": [27.0, 26.0],
        "precipitation_sum": [0.0, 8.5],
        "rain_sum": [0.0, 8.5],
        "snowfall_sum": [0.0, 0.0],
        "precipitation_probability_max": [10, 75],
        "wind_speed_10m_max": [15.0, 22.0],
        "wind_gusts_10m_max": [25.0, 35.0],
        "wind_direction_10m_dominant": [120, 90],
        "uv_index_max": [8.5, 5.0],
        "sunrise": ["2026-09-06T06:02", "2026-09-07T06:03"],
        "sunset": ["2026-09-06T18:35", "2026-09-07T18:34"],
    },
    "hourly": {
        "time": ["2026-09-06T00:00", "2026-09-06T01:00"],
        "temperature_2m": [26.0, 25.5],
        "relative_humidity_2m": [75.0, 78.0],
        "apparent_temperature": [28.0, 27.5],
        "precipitation_probability": [0, 5],
        "precipitation": [0.0, 0.0],
        "weather_code": [0, 0],
        "wind_speed_10m": [8.0, 7.5],
        "is_day": [0, 0],
    },
}


async def test_openmeteo_fetch_current_offline():
    """Verify Open-Meteo fetch_current parses fields deterministically offline."""
    client = OpenMeteoClient()

    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert "/forecast" in request.url.path
        return httpx.Response(200, json=SAMPLE_OPENMETEO_CURRENT_RESPONSE)

    # Inject mock transport
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(mock_handler),
        base_url="https://api.open-meteo.com/v1",
    )

    try:
        point = await client.fetch_current(28.6139, 77.2090)
        assert point.source == "open-meteo"
        assert point.temperature_c == 31.5
        assert point.humidity_pct == 68.0
        assert point.feels_like_c == 36.2
        assert point.weather_code == 1
        assert point.weather_description == "Mainly clear"
        assert point.is_day is True
        assert point.wind_speed_kmh == 12.4
    finally:
        await client.close()


async def test_openmeteo_fetch_forecast_offline():
    """Verify Open-Meteo fetch_forecast parses daily and hourly items deterministically."""
    client = OpenMeteoClient()

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=SAMPLE_OPENMETEO_FORECAST_RESPONSE)

    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(mock_handler),
        base_url="https://api.open-meteo.com/v1",
    )

    try:
        timeline = await client.fetch_forecast(28.6139, 77.2090, days=2, include_hourly=True)
        assert timeline.source == "open-meteo"
        assert len(timeline.daily) == 2
        assert timeline.daily[0].temp_max_c == 34.0
        assert timeline.daily[1].precipitation_sum_mm == 8.5
        assert timeline.hourly is not None
        assert len(timeline.hourly) == 2
    finally:
        await client.close()


async def test_openmeteo_retry_on_transient_error():
    """Verify Open-Meteo client retries upon receiving 429 and succeeds on subsequent try."""
    client = OpenMeteoClient()
    attempts = 0

    def mock_flaky(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, json={"error": "Rate limit exceeded"})
        return httpx.Response(200, json=SAMPLE_OPENMETEO_CURRENT_RESPONSE)

    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(mock_flaky),
        base_url="https://api.open-meteo.com/v1",
    )

    try:
        point = await client.fetch_current(28.6139, 77.2090)
        assert point.temperature_c == 31.5
        assert attempts == 2
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# Location Resolver Offline & Fallback Tests
# ---------------------------------------------------------------------------


async def test_location_resolver_gazetteer_instant():
    """Verify built-in gazetteer resolves Indian states and cities with 0 network calls."""
    # State test
    matches = await resolve_location("Odisha")
    assert len(matches) == 1
    assert matches[0].name == "Odisha"
    assert matches[0].country_code == "IN"
    assert matches[0].confidence == 1.0

    # City test
    mumbai_matches = await resolve_location("Mumbai")
    assert len(mumbai_matches) == 1
    assert mumbai_matches[0].name == "Mumbai"
    assert round(mumbai_matches[0].lat, 2) == 19.08
    assert round(mumbai_matches[0].lon, 2) == 72.88


async def test_location_resolver_geocoding_mock(monkeypatch):
    """Verify geocoding resolution with mocked Open-Meteo geocoding response."""
    geocoding_data = {
        "results": [
            {
                "id": 1273874,
                "name": "Kochi",
                "latitude": 9.9399,
                "longitude": 76.2602,
                "country": "India",
                "country_code": "IN",
                "admin1": "Kerala",
            }
        ]
    }

    mock_transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json=geocoding_data)
    )

    # Monkeypatch httpx.AsyncClient to use mock_transport
    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *args, **kwargs: real_async_client(transport=mock_transport, *args, **kwargs),
    )

    matches = await resolve_location("Kochi")
    assert len(matches) == 1
    assert matches[0].name == "Kochi"
    assert matches[0].country_code == "IN"
    assert matches[0].admin1 == "Kerala"


async def test_location_resolver_offline_fallback(monkeypatch):
    """Verify location resolver falls back to local gazetteer when geocoding network fails."""
    # Transport that always times out
    mock_transport = httpx.MockTransport(
        lambda req: (_ for _ in ()).throw(httpx.ConnectTimeout("Network is unreachable"))
    )

    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *args, **kwargs: real_async_client(transport=mock_transport, *args, **kwargs),
    )

    # "Jaipur City" is not an exact match key, but contains "jaipur"
    matches = await resolve_location("Jaipur City")
    assert len(matches) == 1
    assert matches[0].name == "Jaipur"
    assert matches[0].confidence == 0.8
