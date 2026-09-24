from backend.app.models import (
    FarmerProfile,
    FarmerCrop,
    Conversation,
    QueryLog,
    ResponseLog,
    SourceDocument,
    KnowledgeChunk,
    GovernmentScheme,
    MandiPrice,
    SyncLog,
)


def test_model_imports_and_table_names():
    """Verify that all core database models are importable and have expected table names."""
    assert FarmerProfile.__tablename__ == "farmer_profiles"
    assert FarmerCrop.__tablename__ == "farmer_crops"
    assert Conversation.__tablename__ == "conversations"
    assert QueryLog.__tablename__ == "query_logs"
    assert ResponseLog.__tablename__ == "response_logs"
    assert SourceDocument.__tablename__ == "source_documents"
    assert KnowledgeChunk.__tablename__ == "knowledge_chunks"
    assert GovernmentScheme.__tablename__ == "government_schemes"
    assert MandiPrice.__tablename__ == "mandi_prices"
    assert SyncLog.__tablename__ == "sync_logs"


def test_extensible_knowledge_chunk_fields():
    """Verify that KnowledgeChunk supports extensible agronomic metadata."""
    chunk = KnowledgeChunk(
        crop_name="Millets",
        state="Karnataka",
        season="Kharif",
        growth_stage="Vegetative",
        topic="Nutrient Management",
        content="Apply organic compost at early vegetative stage.",
        content_hash="abc123hash",
        token_count=12,
        chunk_metadata={"source_authority": "UAS Bangalore", "verified": True},
    )
    assert chunk.crop_name == "Millets"
    assert chunk.state == "Karnataka"
    assert chunk.season == "Kharif"
    assert chunk.chunk_metadata["source_authority"] == "UAS Bangalore"


def test_mandi_price_data_origin():
    """Verify that MandiPrice requires clear separation of data origin."""
    price = MandiPrice(
        state="Madhya Pradesh",
        district="Ujjain",
        market="Ujjain",
        commodity="Wheat",
        arrival_date="2026-09-22",
        min_price=2400.0,
        max_price=2650.0,
        modal_price=2520.0,
        source="Agmarknet / data.gov.in",
        data_origin="production_live",
    )
    assert price.data_origin == "production_live"
    assert price.commodity == "Wheat"


def test_source_document_provenance_and_chunk_index():
    """Verify that SourceDocument supports content_hash, language, and chunk_index."""
    doc = SourceDocument(
        title="Test POP",
        source_name="ICAR-Test",
        source_type="ICAR",
        issuing_authority="ICAR",
        content_hash="test_sha256_hash",
        language="hi",
        doc_metadata={"crop": "Paddy"},
    )
    assert doc.source_name == "ICAR-Test"
    assert doc.content_hash == "test_sha256_hash"
    assert doc.language == "hi"

    chunk = KnowledgeChunk(
        chunk_index=3,
        content="Step 3: Fertilizer application",
        content_hash="hash_step3",
        token_count=5,
    )
    assert chunk.chunk_index == 3

