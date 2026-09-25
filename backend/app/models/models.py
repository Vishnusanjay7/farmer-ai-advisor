import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import (
    Column,
    String,
    Text,
    Boolean,
    Integer,
    Numeric,
    DateTime,
    Date,
    ForeignKey,
    JSON,
    Index,
    Uuid,
)
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from backend.app.db.session import Base


def utc_now():
    return datetime.now(timezone.utc)


class FarmerProfile(Base):
    __tablename__ = "farmer_profiles"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(64), unique=True, nullable=False, index=True)
    phone_number = Column(String(15), unique=True, nullable=True)
    full_name = Column(String(100), nullable=True)
    preferred_language = Column(String(10), nullable=False, default="hi-IN")
    state = Column(String(50), nullable=False, index=True)
    district = Column(String(50), nullable=False, index=True)
    sub_district = Column(String(50), nullable=True)
    village = Column(String(100), nullable=True)
    land_holding_acres = Column(Numeric(6, 2), default=1.0)
    soil_type = Column(String(50), nullable=True)
    irrigation_source = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    crops = relationship("FarmerCrop", back_populates="farmer", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="farmer", cascade="all, delete-orphan")


class FarmerCrop(Base):
    __tablename__ = "farmer_crops"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    farmer_id = Column(String(36), ForeignKey("farmer_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    crop_name = Column(String(50), nullable=False)
    variety = Column(String(50), nullable=True)
    sowing_date = Column(Date, nullable=True)
    acreage = Column(Numeric(5, 2), nullable=True)
    stage = Column(String(30), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    farmer = relationship("FarmerProfile", back_populates="crops")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    farmer_id = Column(String(36), ForeignKey("farmer_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(150), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    farmer = relationship("FarmerProfile", back_populates="conversations")
    queries = relationship("QueryLog", back_populates="conversation", cascade="all, delete-orphan")


class QueryLog(Base):
    __tablename__ = "query_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(Uuid(as_uuid=False), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    farmer_id = Column(String(36), ForeignKey("farmer_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    input_channel = Column(String(20), default="voice", nullable=False)  # 'voice' | 'text'
    audio_storage_path = Column(String(255), nullable=True)
    detected_language = Column(String(10), nullable=False)
    raw_transcript = Column(Text, nullable=False)
    classified_intent = Column(String(50), nullable=False, index=True)
    extracted_entities = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    conversation = relationship("Conversation", back_populates="queries")
    response = relationship("ResponseLog", back_populates="query", uselist=False, cascade="all, delete-orphan")


class ResponseLog(Base):
    __tablename__ = "response_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    query_id = Column(String(36), ForeignKey("query_logs.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    response_text = Column(Text, nullable=False)
    audio_response_path = Column(String(255), nullable=True)
    is_grounded = Column(Boolean, default=True, nullable=False)
    confidence_score = Column(Numeric(4, 3), nullable=True)
    disclaimer_applied = Column(Boolean, default=False, nullable=False)
    retrieved_sources = Column(JSON, default=list, nullable=False)
    latency_breakdown_ms = Column(JSON, default=dict, nullable=False)
    farmer_feedback = Column(String(20), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    query = relationship("QueryLog", back_populates="response")


class SourceDocument(Base):
    __tablename__ = "source_documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(255), nullable=False)
    source_name = Column(String(150), nullable=True)  # e.g., 'ICAR-IIRR Rice POP 2024'
    source_type = Column(String(50), nullable=False)  # 'ICAR', 'SAU_POP', 'KVK', 'CIBRC', 'GOV_PORTAL'
    issuing_authority = Column(String(150), nullable=False)
    state_applicability = Column(String(50), default="All-India", nullable=False)
    agro_climatic_zone = Column(String(100), nullable=True)
    official_document_url = Column(String(500), nullable=True)
    publication_year = Column(Integer, nullable=True)
    version = Column(String(30), nullable=True)
    verified_by_expert = Column(Boolean, default=True, nullable=False)
    source_date = Column(Date, nullable=True)
    content_hash = Column(String(64), unique=True, nullable=True, index=True)
    fetched_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    language = Column(String(10), default="en", nullable=False)
    doc_metadata = Column("metadata", JSON, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    chunks = relationship("KnowledgeChunk", back_populates="document", cascade="all, delete-orphan", order_by="KnowledgeChunk.chunk_index")


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(36), ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = Column(Integer, default=0, nullable=False)  # Preserves document order
    # Extensible metadata architecture (not limited to 5 crops)
    crop_name = Column(String(100), nullable=True, index=True)
    state = Column(String(50), nullable=True, index=True)
    language = Column(String(10), default="en", nullable=False)
    season = Column(String(30), nullable=True)         # 'Kharif', 'Rabi', 'Zaid'
    growth_stage = Column(String(50), nullable=True)   # 'Sowing', 'Vegetative', 'Flowering', 'Harvesting'
    topic = Column(String(100), nullable=True, index=True) # 'Pest Management', 'Fertilizer', 'Irrigation'
    content = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False)
    token_count = Column(Integer, nullable=False)
    chunk_metadata = Column("metadata", JSON, default=dict, nullable=False)
    # pgvector embedding column (768 dimensions)
    embedding = Column(Vector(768), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    document = relationship("SourceDocument", back_populates="chunks")


class GovernmentScheme(Base):
    __tablename__ = "government_schemes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scheme_code = Column(String(50), unique=True, nullable=False, index=True)
    scheme_name = Column(String(255), nullable=False)
    name_translations = Column(JSON, default=dict, nullable=False)
    short_description = Column(Text, nullable=False)
    benefits_summary = Column(Text, nullable=False)
    eligibility_criteria = Column(JSON, default=list, nullable=False)
    required_documents = Column(JSON, default=list, nullable=False)
    application_process = Column(Text, nullable=False)
    official_portal_url = Column(String(500), nullable=False)
    sponsoring_agency = Column(String(100), nullable=False)
    state_scope = Column(String(50), default="Central", nullable=False, index=True)
    last_verified_date = Column(Date, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class MandiPrice(Base):
    __tablename__ = "mandi_prices"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    state = Column(String(50), nullable=False, index=True)
    district = Column(String(50), nullable=False, index=True)
    market = Column(String(100), nullable=False)
    commodity = Column(String(100), nullable=False, index=True)
    variety = Column(String(100), default="Common", nullable=False)
    grade = Column(String(50), default="FAQ", nullable=False)
    arrival_date = Column(Date, nullable=False, index=True)
    min_price = Column(Numeric(10, 2), nullable=False)
    max_price = Column(Numeric(10, 2), nullable=False)
    modal_price = Column(Numeric(10, 2), nullable=False)
    source = Column(String(100), default="Agmarknet / data.gov.in", nullable=False)
    # Clear semantic separation: 'production_live', 'production_cached', 'development_seed'
    data_origin = Column(String(30), default="production_live", nullable=False)
    fetched_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class SyncLog(Base):
    __tablename__ = "sync_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    sync_source = Column(String(50), nullable=False, index=True)  # 'AGMARKNET_DATA_GOV_IN', 'ICAR_POP_INGEST'
    status = Column(String(20), nullable=False)                   # 'SUCCESS', 'FAILED', 'PARTIAL'
    records_processed = Column(Integer, default=0, nullable=False)
    records_inserted = Column(Integer, default=0, nullable=False)
    records_updated = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)
    execution_time_seconds = Column(Numeric(8, 2), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
