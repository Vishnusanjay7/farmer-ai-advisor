import io
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.api.deps import get_stt_provider, get_tts_provider
from backend.app.providers.stt_provider import MockSTTProvider
from backend.app.providers.tts_provider import MockTTSProvider
from tests.test_audio_validator import VALID_WAV_BYTES

client = TestClient(app)


def test_get_languages_endpoint():
    resp = client.get("/api/v1/voice/languages")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_languages"] >= 6
    codes = [l["code"] for l in data["languages"]]
    assert "hi-IN" in codes
    assert "te-IN" in codes
    assert "ta-IN" in codes


def test_stt_success_with_dependency_override():
    app.dependency_overrides[get_stt_provider] = lambda: MockSTTProvider(
        mock_transcript="వరిలో పురుగు నివారణ", mock_lang="te-IN"
    )

    file_tuple = ("test_audio.wav", io.BytesIO(VALID_WAV_BYTES), "audio/wav")
    resp = client.post(
        "/api/v1/voice/stt",
        files={"audio_file": file_tuple},
        data={"language": "te-IN"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["transcript"] == "వరిలో పురుగు నివారణ"
    assert data["detected_language"] == "te-IN"
    assert data["confidence"] > 0.9

    app.dependency_overrides.clear()


def test_stt_empty_audio_validation_failure():
    empty_file = ("empty.wav", io.BytesIO(b""), "audio/wav")
    resp = client.post(
        "/api/v1/voice/stt",
        files={"audio_file": empty_file},
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data["detail"]["error_code"] == "EMPTY_AUDIO_FILE"


def test_stt_invalid_container_header_failure():
    fake_audio = ("bad.wav", io.BytesIO(b"Not An Audio File Header Plain Text"), "audio/wav")
    resp = client.post(
        "/api/v1/voice/stt",
        files={"audio_file": fake_audio},
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data["detail"]["error_code"] == "INVALID_AUDIO_FORMAT"


def test_tts_success_with_dependency_override():
    app.dependency_overrides[get_tts_provider] = lambda: MockTTSProvider()

    resp = client.post(
        "/api/v1/voice/tts",
        json={"text": "आज बाराबंकी में गेहूं का भाव क्या है?", "language": "hi-IN"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["audio_base64"].startswith("UklGRi")
    assert data["audio_format"] == "wav"

    app.dependency_overrides.clear()


def test_tts_validation_failure_empty_text():
    resp = client.post(
        "/api/v1/voice/tts",
        json={"text": "", "language": "hi-IN"},
    )
    assert resp.status_code == 422  # Pydantic min_length validation error


def test_tts_unsupported_language():
    app.dependency_overrides[get_tts_provider] = lambda: MockTTSProvider()
    resp = client.post(
        "/api/v1/voice/tts",
        json={"text": "Test speech", "language": "fr-FR"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error_code"] == "TTS_VALIDATION_ERROR"
    app.dependency_overrides.clear()
