from typing import Dict, List, Optional
from pydantic import BaseModel


class LanguageConfig(BaseModel):
    code: str                     # BCP-47 language tag (e.g., 'hi-IN')
    name: str                     # English name
    native_name: str              # Native script name
    stt_supported: bool           # Whether Sarvam STT supports this language
    stt_model: str                # e.g., 'saaras:v3'
    tts_supported: bool           # Whether Sarvam TTS supports this language
    tts_model: str                # e.g., 'bulbul:v3'
    default_speaker: str          # Default speaker voice (e.g., 'shubh')
    available_speakers: List[str] # List of supported voices


# Centralized Language Registry based on current official Sarvam AI API documentation
# Models: Saaras (STT) and Bulbul v3 (TTS)
LANGUAGE_REGISTRY: Dict[str, LanguageConfig] = {
    "hi-IN": LanguageConfig(
        code="hi-IN",
        name="Hindi",
        native_name="हिंदी",
        stt_supported=True,
        stt_model="saaras:v3",
        tts_supported=True,
        tts_model="bulbul:v3",
        default_speaker="shubh",
        available_speakers=["shubh", "arvind", "amartya", "meera", "kavya"],
    ),
    "te-IN": LanguageConfig(
        code="te-IN",
        name="Telugu",
        native_name="తెలుగు",
        stt_supported=True,
        stt_model="saaras:v3",
        tts_supported=True,
        tts_model="bulbul:v3",
        default_speaker="shubh",
        available_speakers=["shubh", "arvind", "meera", "kavya"],
    ),
    "ta-IN": LanguageConfig(
        code="ta-IN",
        name="Tamil",
        native_name="தமிழ்",
        stt_supported=True,
        stt_model="saaras:v3",
        tts_supported=True,
        tts_model="bulbul:v3",
        default_speaker="shubh",
        available_speakers=["shubh", "arvind", "meera", "kavya"],
    ),
    "mr-IN": LanguageConfig(
        code="mr-IN",
        name="Marathi",
        native_name="मराठी",
        stt_supported=True,
        stt_model="saaras:v3",
        tts_supported=True,
        tts_model="bulbul:v3",
        default_speaker="shubh",
        available_speakers=["shubh", "arvind", "meera", "kavya"],
    ),
    "kn-IN": LanguageConfig(
        code="kn-IN",
        name="Kannada",
        native_name="ಕನ್ನಡ",
        stt_supported=True,
        stt_model="saaras:v3",
        tts_supported=True,
        tts_model="bulbul:v3",
        default_speaker="shubh",
        available_speakers=["shubh", "arvind", "meera", "kavya"],
    ),
    "en-IN": LanguageConfig(
        code="en-IN",
        name="Indian English",
        native_name="English",
        stt_supported=True,
        stt_model="saaras:v3",
        tts_supported=True,
        tts_model="bulbul:v3",
        default_speaker="shubh",
        available_speakers=["shubh", "arvind", "meera", "kavya"],
    ),
    "bn-IN": LanguageConfig(
        code="bn-IN",
        name="Bengali",
        native_name="বাংলা",
        stt_supported=True,
        stt_model="saaras:v3",
        tts_supported=True,
        tts_model="bulbul:v3",
        default_speaker="shubh",
        available_speakers=["shubh", "arvind", "meera", "kavya"],
    ),
    "gu-IN": LanguageConfig(
        code="gu-IN",
        name="Gujarati",
        native_name="ગુજરાતી",
        stt_supported=True,
        stt_model="saaras:v3",
        tts_supported=True,
        tts_model="bulbul:v3",
        default_speaker="shubh",
        available_speakers=["shubh", "arvind", "meera", "kavya"],
    ),
    "ml-IN": LanguageConfig(
        code="ml-IN",
        name="Malayalam",
        native_name="മലയാളം",
        stt_supported=True,
        stt_model="saaras:v3",
        tts_supported=True,
        tts_model="bulbul:v3",
        default_speaker="shubh",
        available_speakers=["shubh", "arvind", "meera", "kavya"],
    ),
    "od-IN": LanguageConfig(
        code="od-IN",
        name="Odia",
        native_name="ଓଡ଼ିଆ",
        stt_supported=True,
        stt_model="saaras:v3",
        tts_supported=True,
        tts_model="bulbul:v3",
        default_speaker="shubh",
        available_speakers=["shubh", "arvind", "meera", "kavya"],
    ),
    "pa-IN": LanguageConfig(
        code="pa-IN",
        name="Punjabi",
        native_name="ਪੰਜਾਬੀ",
        stt_supported=True,
        stt_model="saaras:v3",
        tts_supported=True,
        tts_model="bulbul:v3",
        default_speaker="shubh",
        available_speakers=["shubh", "arvind", "meera", "kavya"],
    ),
}


def get_language_config(code: str) -> Optional[LanguageConfig]:
    """Retrieves language configuration by BCP-47 code or None if not registered."""
    return LANGUAGE_REGISTRY.get(code.strip())


def is_stt_supported(code: str) -> bool:
    """Checks whether the requested language code is supported for STT."""
    config = get_language_config(code)
    return config is not None and config.stt_supported


def is_tts_supported(code: str) -> bool:
    """Checks whether the requested language code is supported for TTS."""
    config = get_language_config(code)
    return config is not None and config.tts_supported
