from backend.app.core.config import settings
from backend.app.providers.base import SpeechToTextProvider, TextToSpeechProvider
from backend.app.providers.stt_provider import SarvamSTTProvider
from backend.app.providers.tts_provider import SarvamTTSProvider


def get_stt_provider() -> SpeechToTextProvider:
    """Dependency provider returning configured STT provider."""
    if settings.ENVIRONMENT in ("production", "staging") and not settings.SARVAM_API_KEY:
        raise ValueError(
            f"SARVAM_API_KEY is required in {settings.ENVIRONMENT} mode for Speech-to-Text."
        )
    return SarvamSTTProvider(api_key=settings.SARVAM_API_KEY)


def get_tts_provider() -> TextToSpeechProvider:
    """Dependency provider returning configured TTS provider."""
    if settings.ENVIRONMENT in ("production", "staging") and not settings.SARVAM_API_KEY:
        raise ValueError(
            f"SARVAM_API_KEY is required in {settings.ENVIRONMENT} mode for Text-to-Speech."
        )
    return SarvamTTSProvider(api_key=settings.SARVAM_API_KEY)
