import pytest
from backend.app.services.audio_validator import (
    validate_audio_payload,
    AudioValidationError,
    MAX_AUDIO_SIZE_BYTES,
)

# Minimal 44-byte standard valid RIFF/WAVE container header
VALID_WAV_BYTES = b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x11+\x00\x00\"V\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"

# Minimal WebM magic bytes
VALID_WEBM_BYTES = b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81\x01\x42\xf7\x81\x01\x42\xf2\x81"

# Minimal MP3 ID3 header
VALID_MP3_BYTES = b"ID3\x04\x00\x00\x00\x00\x00\x23" + b"\x00" * 30


def test_valid_audio_signatures():
    # Valid WAV
    ok, err = validate_audio_payload(VALID_WAV_BYTES, content_type="audio/wav")
    assert ok is True
    assert err is None

    # Valid WebM
    ok, err = validate_audio_payload(VALID_WEBM_BYTES, content_type="audio/webm")
    assert ok is True
    assert err is None

    # Valid MP3
    ok, err = validate_audio_payload(VALID_MP3_BYTES, content_type="audio/mpeg")
    assert ok is True
    assert err is None


def test_empty_audio_rejection():
    with pytest.raises(AudioValidationError) as exc:
        validate_audio_payload(b"")
    assert exc.value.error_code == "EMPTY_AUDIO_FILE"


def test_oversized_audio_rejection():
    # Create fake oversized byte payload
    oversized = b"RIFF" + (b"\x00" * (MAX_AUDIO_SIZE_BYTES + 100))
    with pytest.raises(AudioValidationError) as exc:
        validate_audio_payload(oversized, content_type="audio/wav")
    assert exc.value.error_code == "AUDIO_FILE_TOO_LARGE"


def test_unsupported_mime_type_rejection():
    with pytest.raises(AudioValidationError) as exc:
        validate_audio_payload(VALID_WAV_BYTES, content_type="video/mp4")
    assert exc.value.error_code == "UNSUPPORTED_MIME_TYPE"


def test_invalid_audio_header_rejection():
    # Arbitrary text bytes
    fake_audio = b"<html><body>This is a webpage, not audio</body></html>"
    with pytest.raises(AudioValidationError) as exc:
        validate_audio_payload(fake_audio, content_type="audio/wav")
    assert exc.value.error_code == "INVALID_AUDIO_FORMAT"
