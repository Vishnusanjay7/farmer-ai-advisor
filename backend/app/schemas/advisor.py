import uuid
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator


class AgriculturalIntent(str, Enum):
    CROP_ADVISORY = "CROP_ADVISORY"
    PEST_DISEASE = "PEST_DISEASE"
    GOVERNMENT_SCHEME = "GOVERNMENT_SCHEME"
    MANDI_PRICE = "MANDI_PRICE"
    FERTILIZER = "FERTILIZER"
    IRRIGATION = "IRRIGATION"
    SEED_SELECTION = "SEED_SELECTION"
    SEED_TREATMENT = "SEED_TREATMENT"
    SOIL_MANAGEMENT = "SOIL_MANAGEMENT"
    WEED_MANAGEMENT = "WEED_MANAGEMENT"
    CROP_INSURANCE = "CROP_INSURANCE"
    AGRICULTURAL_CREDIT = "AGRICULTURAL_CREDIT"
    POST_HARVEST = "POST_HARVEST"
    STORAGE = "STORAGE"
    HARVESTING = "HARVESTING"
    GENERAL_AGRICULTURE = "GENERAL_AGRICULTURE"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"


class AuthUser(BaseModel):
    id: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[str] = "authenticated"


class FarmerContextDTO(BaseModel):
    crop: Optional[str] = None
    commodity: Optional[str] = None
    variety: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    market: Optional[str] = None
    season: Optional[str] = None
    growth_stage: Optional[str] = None
    pest_disease: Optional[str] = None
    language: Optional[str] = None


class EvidenceItemDTO(BaseModel):
    evidence_id: str
    source_document_id: Optional[str] = None
    source_name: str
    title: str
    issuing_authority: str
    official_url: Optional[str] = None
    chunk_id: Optional[str] = None
    chunk_index: Optional[int] = None
    content: str
    relevance_score: float = 0.0
    source_date: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    data_origin: str = "production_live"
    status: str = "authoritative"  # authoritative, sufficient, insufficient, rejected


class CitationDTO(BaseModel):
    title: str
    issuing_authority: str
    official_url: Optional[str] = None
    relevance_score: float = 0.0
    data_origin: Optional[str] = None
    arrival_date: Optional[str] = None


class AdvisorQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Farmer query in text or transcribed voice")
    language: str = Field(default="hi-IN", description="Language code (e.g. hi-IN, te-IN, en-IN)")
    input_channel: str = Field(default="text", pattern="^(voice|text)$", description="Input channel ('voice' or 'text')")
    farmer_context: Optional[FarmerContextDTO] = None
    conversation_id: Optional[str] = Field(default=None, description="Optional UUID string of the conversation")

    @field_validator("conversation_id", mode="before")
    @classmethod
    def validate_conversation_id(cls, v: Any) -> Optional[str]:
        if v is None or v == "":
            return None
        v_str = str(v).strip()
        if not v_str:
            return None
        try:
            return str(uuid.UUID(v_str))
        except (ValueError, AttributeError):
            raise ValueError(f"Invalid conversation_id '{v}'. Must be a valid UUID.")


class AdvisorQueryResponse(BaseModel):
    query_id: str
    conversation_id: str
    original_query: str
    normalized_query: str
    language: str
    intent: str
    input_channel: str = "text"
    extracted_context: Dict[str, Any] = Field(default_factory=dict)
    inherited_context: Dict[str, Any] = Field(default_factory=dict)
    response_text: str
    evidence: List[EvidenceItemDTO] = Field(default_factory=list)
    citations: List[CitationDTO] = Field(default_factory=list)
    is_grounded: bool = True
    abstained: bool = False
    abstention_reason: Optional[str] = None
    data_origin: Optional[str] = None
    llm_called: bool = False
    response_category: Optional[str] = None


class ConversationTurnDTO(BaseModel):
    query_id: str
    conversation_id: str
    input_channel: str
    detected_language: str
    query_text: str
    classified_intent: str
    extracted_entities: Dict[str, Any] = Field(default_factory=dict)
    response_text: str
    is_grounded: bool
    disclaimer_applied: bool
    citations: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: str


class ConversationHistoryResponse(BaseModel):
    conversation_id: str
    title: Optional[str] = None
    total_turns: int
    turns: List[ConversationTurnDTO] = Field(default_factory=list)


class ConversationSummaryDTO(BaseModel):
    id: str
    title: Optional[str] = None
    created_at: str
    updated_at: str
    total_turns: int
    last_query: Optional[str] = None
    detected_language: Optional[str] = None


class ConversationListResponse(BaseModel):
    total: int
    conversations: List[ConversationSummaryDTO] = Field(default_factory=list)
