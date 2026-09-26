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


def test_conversation_and_query_log_uuid_mapping():
    """Regression test ensuring Conversation.id and QueryLog.conversation_id use Uuid type compatible with PostgreSQL/Psycopg 3."""
    import uuid
    from sqlalchemy import create_engine, Uuid
    from sqlalchemy.orm import sessionmaker
    from backend.app.db.session import Base

    # 1. Type inspection
    assert isinstance(FarmerProfile.id.type, Uuid)
    assert FarmerProfile.id.type.as_uuid is False
    assert isinstance(Conversation.id.type, Uuid)
    assert Conversation.id.type.as_uuid is False
    assert isinstance(Conversation.farmer_id.type, Uuid)
    assert Conversation.farmer_id.type.as_uuid is False
    assert isinstance(QueryLog.id.type, Uuid)
    assert QueryLog.id.type.as_uuid is False
    assert isinstance(QueryLog.conversation_id.type, Uuid)
    assert QueryLog.conversation_id.type.as_uuid is False
    assert isinstance(QueryLog.farmer_id.type, Uuid)
    assert QueryLog.farmer_id.type.as_uuid is False
    assert isinstance(ResponseLog.id.type, Uuid)
    assert ResponseLog.id.type.as_uuid is False
    assert isinstance(ResponseLog.query_id.type, Uuid)
    assert ResponseLog.query_id.type.as_uuid is False

    # 2. Functional persistence and query check
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    conv_uuid = str(uuid.uuid4())
    farmer = FarmerProfile(
        id=str(uuid.uuid4()),
        session_id=f"test-sess-{conv_uuid[:8]}",
        state="Punjab",
        district="Ludhiana",
    )
    db.add(farmer)
    db.flush()

    conv = Conversation(id=conv_uuid, farmer_id=farmer.id, title="Test Conversation")
    db.add(conv)
    db.flush()

    query1 = QueryLog(
        id=str(uuid.uuid4()),
        conversation_id=conv_uuid,
        farmer_id=farmer.id,
        detected_language="en-IN",
        raw_transcript="What about yellow rust?",
        classified_intent="PEST_DISEASE",
        extracted_entities={"crop": "Wheat"},
    )
    db.add(query1)
    db.commit()

    # Query by string UUID representation
    fetched_conv = db.query(Conversation).filter(Conversation.id == conv_uuid).first()
    assert fetched_conv is not None
    assert fetched_conv.id == conv_uuid

    fetched_queries = db.query(QueryLog).filter(QueryLog.conversation_id == conv_uuid).all()
    assert len(fetched_queries) == 1
    assert fetched_queries[0].conversation_id == conv_uuid
    assert fetched_queries[0].raw_transcript == "What about yellow rust?"
    assert fetched_queries[0].extracted_entities["crop"] == "Wheat"

    db.close()


def test_mandi_price_uuid_mapping():
    """Regression test ensuring MandiPrice.id uses Uuid type compatible with PostgreSQL/Psycopg 3."""
    import uuid
    from datetime import date
    from sqlalchemy import create_engine, Uuid
    from sqlalchemy.orm import sessionmaker
    from backend.app.db.session import Base

    # 1. Type inspection
    assert isinstance(MandiPrice.id.type, Uuid)
    assert MandiPrice.id.type.as_uuid is False

    # 2. Persistence and query verification
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    test_id = str(uuid.uuid4())
    price = MandiPrice(
        id=test_id,
        state="Madhya Pradesh",
        district="Indore",
        market="Indore",
        commodity="Wheat",
        variety="Lokwan",
        grade="FAQ",
        arrival_date=date(2026, 9, 25),
        min_price=2400.0,
        max_price=2600.0,
        modal_price=2500.0,
        source="Agmarknet / data.gov.in",
        data_origin="production_live",
    )
    db.add(price)
    db.commit()

    # Query by string UUID
    fetched = db.query(MandiPrice).filter(MandiPrice.id == test_id).first()
    assert fetched is not None
    assert fetched.id == test_id
    assert fetched.commodity == "Wheat"
    assert fetched.modal_price == 2500.0

    # Also verify insertion with default UUID generator
    price_default = MandiPrice(
        state="Madhya Pradesh",
        district="Ujjain",
        market="Ujjain",
        commodity="Soybean",
        variety="Yellow",
        grade="FAQ",
        arrival_date=date(2026, 9, 25),
        min_price=4100.0,
        max_price=4400.0,
        modal_price=4250.0,
    )
    db.add(price_default)
    db.commit()

    assert price_default.id is not None
    assert isinstance(price_default.id, str)
    assert len(price_default.id) == 36

    db.close()



