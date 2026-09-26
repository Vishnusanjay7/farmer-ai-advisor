import pytest
from backend.app.services.audio_validator import (
    validate_audio_payload,
    detect_audio_format,
    AudioValidationError,
    MAX_AUDIO_SIZE_BYTES,
)

# Minimal valid container headers
VALID_WAV_BYTES = b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x11+\x00\x00\"V\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
VALID_WEBM_BYTES = b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81\x01\x42\xf7\x81\x01\x42\xf2\x81"
VALID_OGG_BYTES = b"OggS\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
VALID_MP3_BYTES = b"ID3\x04\x00\x00\x00\x00\x00\x23" + b"\x00" * 30
VALID_MP4_FTYP_BYTES = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
VALID_MP4_STYP_BYTES = b"\x00\x00\x00\x18stypmsix\x00\x00\x00\x00msixisom"  # Fragmented MP4 (Safari / iOS)


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

    # Valid MP4 / M4A (standard ftyp)
    ok, err = validate_audio_payload(VALID_MP4_FTYP_BYTES, content_type="audio/mp4")
    assert ok is True
    assert err is None

    # Valid Fragmented MP4 (styp)
    ok, err = validate_audio_payload(VALID_MP4_STYP_BYTES, content_type="audio/mp4")
    assert ok is True
    assert err is None


def test_detect_audio_format_wav():
    fmt = detect_audio_format(VALID_WAV_BYTES)
    assert fmt.format_name == "wav"
    assert fmt.filename == "audio.wav"
    assert fmt.content_type == "audio/wav"


def test_detect_audio_format_webm():
    fmt = detect_audio_format(VALID_WEBM_BYTES)
    assert fmt.format_name == "webm"
    assert fmt.filename == "audio.webm"
    assert fmt.content_type == "audio/webm"


def test_detect_audio_format_ogg():
    fmt = detect_audio_format(VALID_OGG_BYTES)
    assert fmt.format_name == "ogg"
    assert fmt.filename == "audio.ogg"
    assert fmt.content_type == "audio/ogg"


def test_detect_audio_format_mp3():
    fmt = detect_audio_format(VALID_MP3_BYTES)
    assert fmt.format_name == "mp3"
    assert fmt.filename == "audio.mp3"
    assert fmt.content_type == "audio/mpeg"


def test_detect_audio_format_mp4_ftyp():
    fmt = detect_audio_format(VALID_MP4_FTYP_BYTES)
    assert fmt.format_name == "mp4"
    assert fmt.filename == "audio.mp4"
    assert fmt.content_type == "audio/mp4"


def test_detect_audio_format_mp4_styp():
    fmt = detect_audio_format(VALID_MP4_STYP_BYTES)
    assert fmt.format_name == "mp4"
    assert fmt.filename == "audio.mp4"
    assert fmt.content_type == "audio/mp4"


def test_detect_audio_format_unsupported_rejection():
    with pytest.raises(AudioValidationError) as exc:
        detect_audio_format(b"<html><body>Not an audio container</body></html>")
    assert exc.value.error_code == "INVALID_AUDIO_FORMAT"


def test_empty_audio_rejection():
    with pytest.raises(AudioValidationError) as exc:
        validate_audio_payload(b"")
    assert exc.value.error_code == "EMPTY_AUDIO_FILE"


def test_oversized_audio_rejection():
    oversized = b"RIFF" + (b"\x00" * (MAX_AUDIO_SIZE_BYTES + 100))
    with pytest.raises(AudioValidationError) as exc:
        validate_audio_payload(oversized, content_type="audio/wav")
    assert exc.value.error_code == "AUDIO_FILE_TOO_LARGE"


def test_unsupported_mime_type_rejection():
    with pytest.raises(AudioValidationError) as exc:
        validate_audio_payload(VALID_WAV_BYTES, content_type="video/mp4")
    assert exc.value.error_code == "UNSUPPORTED_MIME_TYPE"


def test_invalid_audio_header_rejection():
    fake_audio = b"<html><body>This is a webpage, not audio</body></html>"
    with pytest.raises(AudioValidationError) as exc:
        validate_audio_payload(fake_audio, content_type="audio/wav")
    assert exc.value.error_code == "INVALID_AUDIO_FORMAT"


def test_no_arbitrary_octet_stream_bypass():
    """application/octet-stream must still be strictly rejected if magic bytes do not match a valid audio container."""
    garbage_bytes = b"SOMERANDOMNONAUDIOBYTESPAYLOAD1234567890"
    with pytest.raises(AudioValidationError) as exc:
        validate_audio_payload(garbage_bytes, content_type="application/octet-stream")
    assert exc.value.error_code == "INVALID_AUDIO_FORMAT"
