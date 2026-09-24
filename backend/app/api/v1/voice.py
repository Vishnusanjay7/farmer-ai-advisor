from typing import Optional
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status

from backend.app.core.logging import logger
from backend.app.core.languages import LANGUAGE_REGISTRY
from backend.app.schemas.voice import STTResponse, TTSRequest, TTSResponse, LanguageListResponse
from backend.app.providers.base import SpeechToTextProvider, TextToSpeechProvider
from backend.app.services.audio_validator import AudioValidationError, validate_audio_payload
from backend.app.api.deps import get_stt_provider, get_tts_provider

router = APIRouter(prefix="/voice", tags=["Voice Services"])


@router.post("/stt", response_model=STTResponse)
async def speech_to_text(
    audio_file: UploadFile = File(..., description="Uploaded audio recording file"),
    language: Optional[str] = Form(None, description="Optional BCP-47 language hint (e.g. 'hi-IN', 'te-IN')"),
    stt_provider: SpeechToTextProvider = Depends(get_stt_provider),
) -> STTResponse:
    """
    Transcribes uploaded audio into regional Indian language text using official Sarvam AI STT (Saaras model).
    Validates audio format, size, and container headers.
    """
    try:
        audio_bytes = await audio_file.read()
    except Exception as exc:
        logger.error(f"Failed reading uploaded audio stream: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "AUDIO_READ_ERROR", "message": "Failed to read uploaded audio file stream."},
        )

    # 1. Audio validation
    try:
        validate_audio_payload(
            audio_bytes,
            content_type=audio_file.content_type,
            filename=audio_file.filename,
        )
    except AudioValidationError as ave:
        logger.warning(f"Audio validation rejected upload: {ave.error_code} - {ave.message}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": ave.error_code, "message": ave.message},
        )

    # 2. Call STT Provider
    try:
        result = await stt_provider.transcribe(audio_bytes, language_hint=language)
        return STTResponse(
            transcript=result.transcript,
            detected_language=result.detected_language,
            confidence=result.confidence,
            duration_seconds=result.duration_seconds,
        )
    except ValueError as ve:
        logger.warning(f"STT validation error: {ve}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "STT_VALIDATION_ERROR", "message": str(ve)},
        )
    except PermissionError as pe:
        logger.error(f"STT authentication error: {pe}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "PROVIDER_AUTH_ERROR", "message": str(pe)},
        )
    except TimeoutError as te:
        logger.error(f"STT timeout: {te}")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={"error_code": "PROVIDER_TIMEOUT", "message": str(te)},
        )
    except Exception as exc:
        logger.error(f"STT upstream error: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error_code": "PROVIDER_ERROR", "message": str(exc)},
        )


@router.post("/tts", response_model=TTSResponse)
async def text_to_speech(
    request: TTSRequest,
    tts_provider: TextToSpeechProvider = Depends(get_tts_provider),
) -> TTSResponse:
    """
    Synthesizes natural regional Indian speech from text using official Sarvam AI TTS (Bulbul model).
    """
    try:
        result = await tts_provider.synthesize(
            text=request.text,
            language_code=request.language,
            speaker=request.speaker,
        )
        return TTSResponse(
            audio_base64=result.audio_base64,
            audio_format=result.audio_format,
            duration_seconds=result.duration_seconds,
        )
    except ValueError as ve:
        logger.warning(f"TTS validation error: {ve}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "TTS_VALIDATION_ERROR", "message": str(ve)},
        )
    except PermissionError as pe:
        logger.error(f"TTS authentication error: {pe}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "PROVIDER_AUTH_ERROR", "message": str(pe)},
        )
    except TimeoutError as te:
        logger.error(f"TTS timeout: {te}")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={"error_code": "PROVIDER_TIMEOUT", "message": str(te)},
        )
    except Exception as exc:
        logger.error(f"TTS upstream error: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error_code": "PROVIDER_ERROR", "message": str(exc)},
        )


@router.get("/languages", response_model=LanguageListResponse)
async def get_supported_languages() -> LanguageListResponse:
    """
    Returns the centralized list of Indian regional languages supported by Sarvam STT and TTS.
    """
    languages = list(LANGUAGE_REGISTRY.values())
    return LanguageListResponse(
        total_languages=len(languages),
        languages=languages,
    )
