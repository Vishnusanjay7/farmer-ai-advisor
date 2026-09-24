from backend.app.core.languages import (
    LANGUAGE_REGISTRY,
    get_language_config,
    is_stt_supported,
    is_tts_supported,
)


def test_supported_languages_registry():
    # Verify core 6 farmer languages + extensions
    expected_codes = ["hi-IN", "te-IN", "ta-IN", "mr-IN", "kn-IN", "en-IN", "bn-IN", "gu-IN", "pa-IN"]
    for code in expected_codes:
        cfg = get_language_config(code)
        assert cfg is not None, f"Expected {code} in language registry"
        assert cfg.stt_supported is True
        assert cfg.tts_supported is True
        assert cfg.stt_model == "saaras:v3"
        assert cfg.tts_model == "bulbul:v3"
        assert len(cfg.available_speakers) > 0


def test_unsupported_language_rejection():
    assert is_stt_supported("fr-FR") is False
    assert is_tts_supported("es-ES") is False
    assert get_language_config("de-DE") is None
