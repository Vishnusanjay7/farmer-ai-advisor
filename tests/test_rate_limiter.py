import io
import time
import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.core.config import settings
from backend.app.core.rate_limiter import (
    InMemoryRateLimiter,
    rate_limiter,
    resolve_client_ip,
    DEFAULT_RATE_LIMITS,
)
from backend.app.api.deps import get_stt_provider, get_tts_provider
from backend.app.api.v1.advisor import get_orchestrator
from backend.app.providers.base import STTResult, TTSResult
from backend.app.schemas.advisor import AdvisorQueryResponse, AgriculturalIntent


# Helper mock WAV bytes
def make_wav_bytes(length=1000) -> bytes:
    return b"RIFF" + (length + 36).to_bytes(4, "little") + b"WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data" + length.to_bytes(4, "little") + (b"\x00" * length)


# =============================================================================
# 1. Request below limit succeeds
# =============================================================================
def test_request_below_limit_succeeds():
    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.headers.get("X-RateLimit-Limit") == "60"
    assert response.headers.get("X-RateLimit-Remaining") == "59"


# =============================================================================
# 2. Request at limit succeeds
# =============================================================================
def test_request_at_limit_succeeds():
    limiter = InMemoryRateLimiter(limits={("GET", "/test"): 3})
    for i in range(3):
        allowed, limit, remaining, retry_after = limiter.check_rate_limit("GET", "/test", "1.1.1.1")
        assert allowed is True
        assert limit == 3
        assert remaining == (3 - (i + 1))


# =============================================================================
# 3. Request above limit returns HTTP 429
# =============================================================================
def test_request_above_limit_returns_429():
    limiter = InMemoryRateLimiter(limits={("GET", "/test"): 2})
    limiter.check_rate_limit("GET", "/test", "1.1.1.1")
    limiter.check_rate_limit("GET", "/test", "1.1.1.1")

    allowed, limit, remaining, retry_after = limiter.check_rate_limit("GET", "/test", "1.1.1.1")
    assert allowed is False
    assert limit == 2
    assert remaining == 0
    assert retry_after > 0


# =============================================================================
# 4. Separate client IPs have separate buckets
# =============================================================================
def test_separate_client_ips_have_separate_buckets():
    limiter = InMemoryRateLimiter(limits={("POST", "/test"): 2})

    # Client A consumes quota
    limiter.check_rate_limit("POST", "/test", "192.168.1.10")
    limiter.check_rate_limit("POST", "/test", "192.168.1.10")
    allowed_a, _, _, _ = limiter.check_rate_limit("POST", "/test", "192.168.1.10")
    assert allowed_a is False

    # Client B should still have full quota
    allowed_b, limit_b, remaining_b, _ = limiter.check_rate_limit("POST", "/test", "192.168.1.20")
    assert allowed_b is True
    assert remaining_b == 1


# =============================================================================
# 5. Expired window allows requests again (Deterministic Fake Time)
# =============================================================================
def test_expired_window_allows_requests_again():
    fake_time = 1000.0
    limiter = InMemoryRateLimiter(limits={("GET", "/test"): 1}, time_func=lambda: fake_time)

    # First request succeeds
    allowed, _, _, _ = limiter.check_rate_limit("GET", "/test", "1.1.1.1")
    assert allowed is True

    # Immediate second request fails
    allowed, _, _, retry_after = limiter.check_rate_limit("GET", "/test", "1.1.1.1")
    assert allowed is False
    assert retry_after == 60

    # Advance time by 61 seconds (past window)
    fake_time = 1061.0
    allowed, _, remaining, _ = limiter.check_rate_limit("GET", "/test", "1.1.1.1")
    assert allowed is True
    assert remaining == 0


# =============================================================================
# 6. Health endpoint has its own configured limit (60/min)
# =============================================================================
def test_health_endpoint_limit_60_per_minute():
    fake_now = 2000.0
    rate_limiter.set_time_func(lambda: fake_now)
    client = TestClient(app)

    # 60 calls succeed
    for _ in range(60):
        res = client.get("/api/v1/health")
        assert res.status_code == 200

    # 61st call returns 429
    res = client.get("/api/v1/health")
    assert res.status_code == 429
    assert res.json()["error_code"] == "RATE_LIMIT_EXCEEDED"
    assert "60 requests per minute" in res.json()["message"]
    assert "Retry-After" in res.headers


# =============================================================================
# 7. Advisor endpoint has 20/minute limit
# =============================================================================
def test_advisor_endpoint_limit_20_per_minute():
    fake_now = 3000.0
    rate_limiter.set_time_func(lambda: fake_now)

    mock_orch = MagicMock()
    mock_orch.answer_query = AsyncMock(
        return_value=AdvisorQueryResponse(
            query_id="test_query_id",
            conversation_id="test_conv_id",
            original_query="Irrigation for wheat",
            normalized_query="irrigation for wheat",
            language="en-IN",
            input_channel="text",
            intent=AgriculturalIntent.CROP_ADVISORY.value,
            is_grounded=True,
            response_text="Irrigate wheat at CRI stage.",
            citations=[],
        )
    )
    app.dependency_overrides[get_orchestrator] = lambda: mock_orch
    client = TestClient(app)

    try:
        # 20 requests succeed
        for _ in range(20):
            res = client.post("/api/v1/advisor/query", json={"query": "test query", "language": "en-IN"})
            assert res.status_code == 200

        # 21st request returns 429
        res = client.post("/api/v1/advisor/query", json={"query": "test query", "language": "en-IN"})
        assert res.status_code == 429
        assert res.json()["error_code"] == "RATE_LIMIT_EXCEEDED"
        assert "20 requests per minute" in res.json()["message"]
    finally:
        app.dependency_overrides.clear()


# =============================================================================
# 8. STT endpoint has 10/minute limit
# =============================================================================
def test_stt_endpoint_limit_10_per_minute():
    fake_now = 4000.0
    rate_limiter.set_time_func(lambda: fake_now)

    mock_stt = MagicMock()
    mock_stt.transcribe = AsyncMock(
        return_value=STTResult(transcript="gehu me sinchai", detected_language="hi-IN", confidence=0.95, duration_seconds=1.0)
    )
    app.dependency_overrides[get_stt_provider] = lambda: mock_stt
    client = TestClient(app)

    wav_bytes = make_wav_bytes()

    try:
        # 10 calls succeed
        for _ in range(10):
            res = client.post(
                "/api/v1/voice/stt",
                files={"audio_file": ("test.wav", io.BytesIO(wav_bytes), "audio/wav")},
                data={"language": "hi-IN"},
            )
            assert res.status_code == 200

        # 11th call returns 429
        res = client.post(
            "/api/v1/voice/stt",
            files={"audio_file": ("test.wav", io.BytesIO(wav_bytes), "audio/wav")},
            data={"language": "hi-IN"},
        )
        assert res.status_code == 429
        assert res.json()["error_code"] == "RATE_LIMIT_EXCEEDED"
        assert "10 requests per minute" in res.json()["message"]
    finally:
        app.dependency_overrides.clear()


# =============================================================================
# 9. TTS endpoint has 10/minute limit
# =============================================================================
def test_tts_endpoint_limit_10_per_minute():
    fake_now = 5000.0
    rate_limiter.set_time_func(lambda: fake_now)

    mock_tts = MagicMock()
    mock_tts.synthesize = AsyncMock(
        return_value=TTSResult(audio_base64="dGVzdGF1ZGlv", audio_format="wav", duration_seconds=1.5)
    )
    app.dependency_overrides[get_tts_provider] = lambda: mock_tts
    client = TestClient(app)

    try:
        # 10 calls succeed
        for _ in range(10):
            res = client.post("/api/v1/voice/tts", json={"text": "namaste kisan", "language": "hi-IN"})
            assert res.status_code == 200

        # 11th call returns 429
        res = client.post("/api/v1/voice/tts", json={"text": "namaste kisan", "language": "hi-IN"})
        assert res.status_code == 429
        assert res.json()["error_code"] == "RATE_LIMIT_EXCEEDED"
        assert "10 requests per minute" in res.json()["message"]
    finally:
        app.dependency_overrides.clear()


# =============================================================================
# 10. Mandi endpoint has 30/minute limit
# =============================================================================
def test_mandi_endpoint_limit_30_per_minute():
    fake_now = 6000.0
    rate_limiter.set_time_func(lambda: fake_now)
    client = TestClient(app)

    # 30 calls succeed
    for _ in range(30):
        res = client.get("/api/v1/mandi/prices?state=Madhya+Pradesh&commodity=Wheat")
        assert res.status_code == 200

    # 31st call returns 429
    res = client.get("/api/v1/mandi/prices?state=Madhya+Pradesh&commodity=Wheat")
    assert res.status_code == 429
    assert res.json()["error_code"] == "RATE_LIMIT_EXCEEDED"
    assert "30 requests per minute" in res.json()["message"]


# =============================================================================
# 11. Rate-limit error does not expose secrets/internal details
# =============================================================================
def test_rate_limit_error_does_not_expose_secrets():
    limiter = InMemoryRateLimiter(limits={("GET", "/api/v1/health"): 1})
    rate_limiter.set_time_func(lambda: 7000.0)
    client = TestClient(app)

    # First succeeds
    client.get("/api/v1/health")
    # Second triggers 429
    for _ in range(65):
        res = client.get("/api/v1/health")

    assert res.status_code == 429
    body = res.json()

    # Verify RFC7807 structure
    assert set(body.keys()) == {"status_code", "error_code", "message", "retry_after"}
    assert body["status_code"] == 429
    assert body["error_code"] == "RATE_LIMIT_EXCEEDED"

    # Verify NO secrets, file paths, or internal implementation details leaked
    res_str = str(body) + str(res.headers)
    for forbidden in ["traceback", "file://", "password", "key", "token", "redis", "postgres", "sql"]:
        assert forbidden not in res_str.lower()


# =============================================================================
# 12. Client IP Resolution & Proxy Header Handling
# =============================================================================
def test_client_ip_proxy_handling():
    req_mock = MagicMock()
    req_mock.headers = {"x-forwarded-for": "203.0.113.195, 70.41.3.18, 150.172.238.178"}
    req_mock.client.host = "10.0.0.1"

    # When trust_proxy_headers=False -> ignores X-Forwarded-For to prevent spoofing
    ip_no_trust = resolve_client_ip(req_mock, trust_proxy_headers=False)
    assert ip_no_trust == "10.0.0.1"

    # When trust_proxy_headers=True -> uses client IP from reverse proxy
    ip_with_trust = resolve_client_ip(req_mock, trust_proxy_headers=True)
    assert ip_with_trust == "203.0.113.195"
