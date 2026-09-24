import base64
import time
from typing import Optional, Dict, Any
import httpx

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.core.languages import is_tts_supported, get_language_config
from backend.app.providers.base import TextToSpeechProvider, TTSResult

# Maximum text length supported by Sarvam bulbul:v3
MAX_TTS_TEXT_LENGTH = 2500


class SarvamTTSProvider(TextToSpeechProvider):
    """
    Official Sarvam AI Text-to-Speech Provider (Bulbul v3 model).
    Synthesizes native speech across 11+ Indian regional languages.
    """

    ENDPOINT = "https://api.sarvam.ai/text-to-speech"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.SARVAM_API_KEY

    async def synthesize(self, text: str, language_code: str, speaker: Optional[str] = None) -> TTSResult:
        # 1. Check API credentials
        if not self.api_key:
            logger.error("Sarvam TTS invoked but SARVAM_API_KEY is missing.")
            raise ValueError(
                "SARVAM_API_KEY is not configured in the environment. Cannot generate real speech."
            )

        # 2. Text validation
        cleaned_text = text.strip()
        if not cleaned_text:
            raise ValueError("TTS text cannot be empty.")
        if len(cleaned_text) > MAX_TTS_TEXT_LENGTH:
            raise ValueError(f"TTS text length ({len(cleaned_text)}) exceeds maximum allowed ({MAX_TTS_TEXT_LENGTH} chars).")

        # 3. Language validation
        if not is_tts_supported(language_code):
            raise ValueError(f"Language '{language_code}' is not supported by Sarvam TTS.")

        lang_cfg = get_language_config(language_code)
        speaker_name = speaker or (lang_cfg.default_speaker if lang_cfg else "shubh")
        model_name = lang_cfg.tts_model if lang_cfg else "bulbul:v3"

        headers = {
            "api-subscription-key": self.api_key,
            "Content-Type": "application/json",
        }

        # Payload formatted per official Sarvam bulbul:v3 specification
        payload = {
            "text": cleaned_text,
            "language_code": language_code,
            "speaker": speaker_name,
            "pace": 1.0,
            "model": model_name,
        }

        logger.info(f"Sending TTS request to Sarvam AI (model={model_name}, lang={language_code}, speaker={speaker_name}, chars={len(cleaned_text)})")
        start_t = time.time()

        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                resp = await client.post(self.ENDPOINT, headers=headers, json=payload)

                if resp.status_code == 401 or resp.status_code == 403:
                    raise PermissionError(f"Sarvam AI authentication failed (HTTP {resp.status_code}): Invalid or inactive API key.")

                if resp.status_code != 200:
                    raise RuntimeError(f"Sarvam TTS failed with HTTP {resp.status_code}: {resp.text}")

                duration = time.time() - start_t
                data = resp.json()

                # Extract base64 audio from 'audios' list or 'audio_content'
                audio_b64 = None
                if "audios" in data and isinstance(data["audios"], list) and len(data["audios"]) > 0:
                    audio_b64 = data["audios"][0]
                elif "audio_content" in data:
                    audio_b64 = data["audio_content"]

                if not audio_b64:
                    raise RuntimeError("Sarvam TTS returned success status but missing audio payload.")

                logger.info(f"Sarvam TTS succeeded in {round(duration, 2)}s (audio size: {len(audio_b64)} b64 chars)")

                return TTSResult(
                    audio_base64=audio_b64,
                    audio_format="wav",
                    duration_seconds=round(duration, 2),
                )

        except httpx.TimeoutException as exc:
            logger.error("Sarvam TTS request timed out after 25s.")
            raise TimeoutError("Text-to-speech service timed out. Please retry.") from exc
        except (PermissionError, ValueError, TimeoutError):
            raise
        except Exception as exc:
            logger.error(f"Sarvam TTS communication failure: {exc}", exc_info=True)
            raise RuntimeError(f"Sarvam TTS upstream error: {str(exc)}") from exc


class MockTTSProvider(TextToSpeechProvider):
    """
    Deterministic Mock TTS Provider strictly for automated unit testing.
    Must never be used in live production farmer interactions.
    """

    # Minimal valid 44-byte standard RIFF/WAVE header in base64
    SAMPLE_WAV_BASE64 = (
        "UklGRiQAAABXQVZFZm10IBAAAAABAAEAESsAACJWAAACABAAZGF0YQAAAAA="
    )

    async def synthesize(self, text: str, language_code: str, speaker: Optional[str] = None) -> TTSResult:
        if not text.strip():
            raise ValueError("TTS text cannot be empty.")
        if not is_tts_supported(language_code):
            raise ValueError(f"Language '{language_code}' is not supported.")

        return TTSResult(
            audio_base64=self.SAMPLE_WAV_BASE64,
            audio_format="wav",
            duration_seconds=0.1,
        )
