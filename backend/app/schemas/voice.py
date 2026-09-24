from typing import Optional, List
from pydantic import BaseModel, Field
from backend.app.core.languages import LanguageConfig


class STTResponse(BaseModel):
    transcript: str = Field(..., description="Recognized speech text")
    detected_language: str = Field(..., description="BCP-47 language tag detected or confirmed")
    confidence: float = Field(..., description="Confidence score between 0.0 and 1.0")
    duration_seconds: float = Field(..., description="Processing duration in seconds")


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2500, description="Text to synthesize")
    language: str = Field(default="hi-IN", description="Target BCP-47 language code (e.g. 'hi-IN', 'te-IN')")
    speaker: Optional[str] = Field(default=None, description="Optional voice name (e.g. 'shubh', 'arvind', 'meera')")


class TTSResponse(BaseModel):
    audio_base64: str = Field(..., description="Base64-encoded audio waveform")
    audio_format: str = Field(default="wav", description="Audio format (wav)")
    duration_seconds: float = Field(..., description="Synthesis processing duration in seconds")


class LanguageListResponse(BaseModel):
    total_languages: int
    languages: List[LanguageConfig]
