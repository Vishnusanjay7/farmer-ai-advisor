import io
import time
from typing import Optional, Dict, Any
import httpx

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.core.languages import is_stt_supported, get_language_config
from backend.app.providers.base import SpeechToTextProvider, STTResult
from backend.app.services.audio_validator import validate_audio_payload, detect_audio_format


class SarvamSTTProvider(SpeechToTextProvider):
    """
    Official Sarvam AI Speech-to-Text Provider (Saaras model).
    Authenticates with 'api-subscription-key' header and submits multipart/form-data.
    """

    ENDPOINT = "https://api.sarvam.ai/speech-to-text"

    def __init__(self, api_key: Optional[str] = None, model: str = "saaras:v3"):
        self.api_key = api_key or settings.SARVAM_API_KEY
        self.model = model

    async def transcribe(self, audio_bytes: bytes, language_hint: Optional[str] = None) -> STTResult:
        # 1. Check API credentials
        if not self.api_key:
            logger.error("Sarvam STT invoked but SARVAM_API_KEY is missing.")
            raise ValueError(
                "SARVAM_API_KEY is not configured in the environment. Cannot perform real speech-to-text."
            )

        # 2. Audio input validation
        validate_audio_payload(audio_bytes)

        # 3. Language support validation
        target_lang = language_hint or "hi-IN"
        if target_lang != "unknown" and not is_stt_supported(target_lang):
            raise ValueError(f"Language '{target_lang}' is not supported by Sarvam STT.")

        lang_cfg = get_language_config(target_lang)
        model_name = lang_cfg.stt_model if lang_cfg else self.model

        # 4. Prepare multipart request per official Sarvam API spec
        fmt_info = detect_audio_format(audio_bytes)
        headers = {
            "api-subscription-key": self.api_key,
        }
        files = {
            "file": (fmt_info.filename, io.BytesIO(audio_bytes), fmt_info.content_type),
        }
        data = {
            "model": model_name,
            "language_code": target_lang,
            "mode": "transcribe",
        }

        logger.info(f"Sending STT request to Sarvam AI (model={model_name}, lang={target_lang}, size={len(audio_bytes)}B)")
        start_t = time.time()

        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                resp = await client.post(self.ENDPOINT, headers=headers, files=files, data=data)

                if resp.status_code == 401 or resp.status_code == 403:
                    raise PermissionError(f"Sarvam AI authentication failed (HTTP {resp.status_code}): Invalid or inactive API key.")

                if resp.status_code != 200:
                    raise RuntimeError(f"Sarvam STT failed with HTTP {resp.status_code}: {resp.text}")

                duration = time.time() - start_t
                payload = resp.json()

                transcript = payload.get("transcript", "").strip()
                detected_lang = payload.get("language_code", target_lang)

                logger.info(f"Sarvam STT succeeded in {round(duration, 2)}s: '{transcript[:60]}...'")

                return STTResult(
                    transcript=transcript,
                    detected_language=detected_lang,
                    confidence=float(payload.get("confidence", 0.95)),
                    duration_seconds=round(duration, 2),
                )

        except httpx.TimeoutException as exc:
            logger.error("Sarvam STT request timed out after 25s.")
            raise TimeoutError("Speech-to-text service timed out. Please retry with shorter audio.") from exc
        except (PermissionError, ValueError, TimeoutError):
            raise
        except Exception as exc:
            logger.error(f"Sarvam STT communication failure: {exc}", exc_info=True)
            raise RuntimeError(f"Sarvam STT upstream error: {str(exc)}") from exc


class MockSTTProvider(SpeechToTextProvider):
    """
    Deterministic Mock STT Provider strictly for unit testing.
    Must never be used in live production farmer interactions.
    """

    def __init__(self, mock_transcript: str = "వరిలో కాండం తొలిచే పురుగు నివారణ ఏమిటి?", mock_lang: str = "te-IN"):
        self.mock_transcript = mock_transcript
        self.mock_lang = mock_lang

    async def transcribe(self, audio_bytes: bytes, language_hint: Optional[str] = None) -> STTResult:
        validate_audio_payload(audio_bytes)
        target_lang = language_hint or self.mock_lang
        return STTResult(
            transcript=self.mock_transcript,
            detected_language=target_lang,
            confidence=0.99,
            duration_seconds=0.1,
        )
