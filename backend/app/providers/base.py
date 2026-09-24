from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


# ==============================================================================
# Provider Transfer Objects (DTOs)
# ==============================================================================

class STTResult(BaseModel):
    transcript: str
    detected_language: str
    confidence: float
    duration_seconds: float


class TTSResult(BaseModel):
    audio_base64: str
    audio_format: str = "wav"
    duration_seconds: float


class MandiPriceDTO(BaseModel):
    state: str
    district: str
    market: str
    commodity: str
    variety: str = "Common"
    grade: str = "FAQ"
    arrival_date: str
    min_price: float
    max_price: float
    modal_price: float
    source: str
    # 'production_live', 'production_cached', or 'development_seed'
    data_origin: str = "production_live"
    fetched_at: str


class GovernmentSchemeDTO(BaseModel):
    id: str
    scheme_code: str
    scheme_name: str
    short_description: str
    benefits_summary: str
    eligibility_criteria: List[str]
    required_documents: List[str]
    application_process: str
    official_portal_url: str
    sponsoring_agency: str
    state_scope: str
    last_verified_date: str


class GroundedSourceCitation(BaseModel):
    document_id: str
    title: str
    issuing_authority: str
    publication_year: Optional[int] = None
    page_or_section: Optional[str] = None
    official_url: Optional[str] = None
    similarity_score: float = 0.0


class LLMGroundedResponse(BaseModel):
    answer_text: str
    language_code: str
    intent: str
    citations: List[GroundedSourceCitation]
    is_grounded: bool
    disclaimer_applied: bool = False
    evidence_sufficient: bool = True


# ==============================================================================
# Abstract Base Interfaces
# ==============================================================================

class SpeechToTextProvider(ABC):
    """Abstract Interface for Regional Indian Speech-to-Text services (e.g., Sarvam Saaras)."""

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, language_hint: Optional[str] = None) -> STTResult:
        """Transcribes raw audio bytes into text with detected language."""
        pass


class TextToSpeechProvider(ABC):
    """Abstract Interface for Regional Indian Text-to-Speech services (e.g., Sarvam Bulbul)."""

    @abstractmethod
    async def synthesize(self, text: str, language_code: str, speaker: Optional[str] = None) -> TTSResult:
        """Synthesizes native speech from given regional language text."""
        pass


class MandiPriceProvider(ABC):
    """Abstract Interface for Agricultural Market Mandi Price retrieval (e.g., Data.gov.in / Agmarknet)."""

    @abstractmethod
    async def get_prices(
        self, state: str, district: Optional[str] = None, commodity: Optional[str] = None
    ) -> List[MandiPriceDTO]:
        """Fetches market prices with clear indication of live vs cached arrival date."""
        pass


class GovernmentSchemeProvider(ABC):
    """Abstract Interface for Government Welfare Scheme discovery (e.g., myScheme, MoA&FW)."""

    @abstractmethod
    async def search_schemes(
        self, query: str, state: Optional[str] = None, category: Optional[str] = None
    ) -> List[GovernmentSchemeDTO]:
        """Retrieves verified government schemes matching criteria."""
        pass


class LLMProvider(ABC):
    """Abstract Interface for LLM generation with strict grounding constraints."""

    @abstractmethod
    async def generate_grounded_response(
        self,
        system_prompt: str,
        user_query: str,
        context_chunks: List[str],
        farmer_context: Optional[Dict[str, Any]] = None,
    ) -> LLMGroundedResponse:
        """
        Generates responses strictly grounded in retrieved evidence.
        Must abstain when authoritative evidence is insufficient.
        """
        pass


class EmbeddingProvider(ABC):
    """Abstract Interface for dense text embedding vector generation."""

    @abstractmethod
    async def generate_embedding(self, text: str) -> List[float]:
        """Generates embedding vector (e.g., 768 dimensions for Gemini text-embedding-004)."""
        pass
