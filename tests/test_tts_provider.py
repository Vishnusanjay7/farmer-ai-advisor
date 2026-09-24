import pytest
from unittest.mock import patch, MagicMock
import httpx
from backend.app.providers.tts_provider import SarvamTTSProvider, MockTTSProvider


@pytest.mark.asyncio
async def test_tts_missing_credentials_raises_error():
    provider = SarvamTTSProvider(api_key=None)
    with pytest.raises(ValueError, match="SARVAM_API_KEY is not configured"):
        await provider.synthesize("नमस्ते किसान भाई", language_code="hi-IN")


@pytest.mark.asyncio
async def test_tts_unsupported_language_raises_error():
    provider = SarvamTTSProvider(api_key="valid_dummy_key")
    with pytest.raises(ValueError, match="is not supported by Sarvam TTS"):
        await provider.synthesize("Hello", language_code="fr-FR")


@pytest.mark.asyncio
async def test_tts_empty_text_raises_error():
    provider = SarvamTTSProvider(api_key="valid_dummy_key")
    with pytest.raises(ValueError, match="cannot be empty"):
        await provider.synthesize("   ", language_code="hi-IN")


@pytest.mark.asyncio
async def test_tts_oversized_text_raises_error():
    provider = SarvamTTSProvider(api_key="valid_dummy_key")
    huge_text = "धान " * 1000  # > 2500 chars
    with pytest.raises(ValueError, match="exceeds maximum allowed"):
        await provider.synthesize(huge_text, language_code="hi-IN")


@pytest.mark.asyncio
async def test_tts_valid_provider_response():
    provider = SarvamTTSProvider(api_key="valid_dummy_key")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "audios": ["UklGRiQAAABXQVZFZm10IBAAAAABAAEAESsAACJWAAACABAAZGF0YQAAAAA="]
    }

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        result = await provider.synthesize("రైతు భరోసా పథకం", language_code="te-IN", speaker="shubh")
        assert result.audio_base64.startswith("UklGRi")
        assert result.audio_format == "wav"
        assert result.duration_seconds >= 0.0


@pytest.mark.asyncio
async def test_tts_authentication_failure():
    provider = SarvamTTSProvider(api_key="invalid_key")

    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.text = "Forbidden: Key expired or quota exceeded"

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        with pytest.raises(PermissionError, match="authentication failed"):
            await provider.synthesize("कृषि योजना", language_code="hi-IN")


@pytest.mark.asyncio
async def test_tts_timeout_failure():
    provider = SarvamTTSProvider(api_key="valid_dummy_key")

    with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Timeout")):
        with pytest.raises(TimeoutError, match="timed out"):
            await provider.synthesize("कृषि योजना", language_code="hi-IN")


@pytest.mark.asyncio
async def test_tts_malformed_response_missing_audio():
    provider = SarvamTTSProvider(api_key="valid_dummy_key")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"audios": []}  # empty list

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        with pytest.raises(RuntimeError, match="missing audio payload"):
            await provider.synthesize("कृषि योजना", language_code="hi-IN")
