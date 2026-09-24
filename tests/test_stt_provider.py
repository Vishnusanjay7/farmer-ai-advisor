import pytest
from unittest.mock import patch, MagicMock
import httpx
from backend.app.providers.stt_provider import SarvamSTTProvider
from tests.test_audio_validator import VALID_WAV_BYTES


@pytest.mark.asyncio
async def test_stt_missing_credentials_raises_error():
    provider = SarvamSTTProvider(api_key=None)
    with pytest.raises(ValueError, match="SARVAM_API_KEY is not configured"):
        await provider.transcribe(VALID_WAV_BYTES, language_hint="hi-IN")


@pytest.mark.asyncio
async def test_stt_unsupported_language_raises_error():
    provider = SarvamSTTProvider(api_key="valid_dummy_key")
    with pytest.raises(ValueError, match="is not supported by Sarvam STT"):
        await provider.transcribe(VALID_WAV_BYTES, language_hint="es-ES")


@pytest.mark.asyncio
async def test_stt_valid_provider_response():
    provider = SarvamSTTProvider(api_key="valid_dummy_key")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "transcript": "धान में तना छेदक कीट का नियंत्रण कैसे करें?",
        "language_code": "hi-IN",
        "confidence": 0.97,
    }

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        result = await provider.transcribe(VALID_WAV_BYTES, language_hint="hi-IN")
        assert result.transcript == "धान में तना छेदक कीट का नियंत्रण कैसे करें?"
        assert result.detected_language == "hi-IN"
        assert result.confidence == 0.97
        assert result.duration_seconds >= 0.0


@pytest.mark.asyncio
async def test_stt_authentication_failure():
    provider = SarvamSTTProvider(api_key="invalid_key")

    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized: Invalid subscription key"

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        with pytest.raises(PermissionError, match="authentication failed"):
            await provider.transcribe(VALID_WAV_BYTES, language_hint="hi-IN")


@pytest.mark.asyncio
async def test_stt_timeout_failure():
    provider = SarvamSTTProvider(api_key="valid_dummy_key")

    with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Connection timed out")):
        with pytest.raises(TimeoutError, match="timed out"):
            await provider.transcribe(VALID_WAV_BYTES, language_hint="hi-IN")


@pytest.mark.asyncio
async def test_stt_malformed_provider_response():
    provider = SarvamSTTProvider(api_key="valid_dummy_key")

    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        with pytest.raises(RuntimeError, match="failed with HTTP 500"):
            await provider.transcribe(VALID_WAV_BYTES, language_hint="hi-IN")
