import pytest
import uuid
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db.session import Base
from backend.app.models.models import (
    SourceDocument,
    KnowledgeChunk,
    GovernmentScheme,
    MandiPrice,
    Conversation,
    QueryLog,
    ResponseLog,
)
from backend.app.schemas.advisor import AdvisorQueryRequest, FarmerContextDTO
from backend.app.services.advisor_orchestrator import AdvisorOrchestrator
from backend.app.services.retrieval_service import RetrievalService
from backend.app.providers.embedding_provider import DeterministicMockEmbeddingProvider
from backend.app.providers.llm_provider import MockLLMProvider


@pytest.fixture
def orchestrator_test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    # Seed 1 source doc and 1 chunk
    doc = SourceDocument(
        id=str(uuid.uuid4()),
        title="ICAR-IIRR Rice POP 2024",
        source_name="ICAR-IIRR",
        source_type="ICAR",
        issuing_authority="ICAR - Indian Institute of Rice Research",
        state_applicability="All-India",
        official_document_url="https://icar-iirr.org/advisory/pop_rice.pdf",
        publication_year=2024,
    )
    db.add(doc)
    db.flush()

    embedder = DeterministicMockEmbeddingProvider(dimension=768)
    vec = embedder.generate_embedding_sync("Yellow stem borer in paddy: Install pheromone traps at 20 traps/ha.")
    c1 = KnowledgeChunk(
        id=str(uuid.uuid4()),
        document_id=doc.id,
        chunk_index=0,
        crop_name="Paddy",
        topic="Pest Management",
        content="Yellow stem borer in paddy: Install pheromone traps at 20 traps/ha.",
        content_hash="hash1",
        token_count=15,
        embedding=vec,
    )
    db.add(c1)

    # Seed Mandi price (Wheat Indore)
    mandi = MandiPrice(
        id=str(uuid.uuid4()),
        state="Madhya Pradesh",
        district="Indore",
        market="Indore",
        commodity="Wheat",
        variety="Lokwan",
        grade="FAQ",
        arrival_date=date(2026, 9, 22),
        min_price=2450.0,
        max_price=2850.0,
        modal_price=2650.0,
        source="Agmarknet",
        data_origin="production_live",
    )
    db.add(mandi)

    # Seed Mandi price (Tomato Tiruppur)
    mandi_tomato = MandiPrice(
        id=str(uuid.uuid4()),
        state="Tamil Nadu",
        district="Tiruppur",
        market="Tiruppur",
        commodity="Tomato",
        variety="Deshi",
        grade="FAQ",
        arrival_date=date(2026, 9, 22),
        min_price=1800.0,
        max_price=2200.0,
        modal_price=2000.0,
        source="Agmarknet",
        data_origin="production_live",
    )
    db.add(mandi_tomato)

    # Seed Scheme
    scheme = GovernmentScheme(
        id=str(uuid.uuid4()),
        scheme_code="PM_KISAN",
        scheme_name="Pradhan Mantri Kisan Samman Nidhi",
        short_description="Direct income support of Rs 6000 per year.",
        benefits_summary="Rs 6,000 per year in three equal installments.",
        eligibility_criteria=["Small and marginal landholder farmer families with landholding"],
        required_documents=["Aadhaar card", "Land records"],
        application_process="Apply online at pmkisan.gov.in",
        official_portal_url="https://pmkisan.gov.in",
        sponsoring_agency="Ministry of Agriculture & Farmers Welfare",
        last_verified_date=date(2026, 9, 22),
        is_active=True,
    )
    db.add(scheme)
    db.commit()

    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.mark.asyncio
async def test_orchestrator_pest_disease_success(orchestrator_test_db):
    retrieval = RetrievalService(embedding_provider=DeterministicMockEmbeddingProvider(dimension=768))
    orchestrator = AdvisorOrchestrator(
        llm_provider=MockLLMProvider(),
        retrieval=retrieval,
    )

    req = AdvisorQueryRequest(
        query="How to control yellow stem borer in paddy?",
        language="en-IN",
    )
    res = await orchestrator.answer_query(db=orchestrator_test_db, request=req)

    assert res.intent == "PEST_DISEASE"
    assert res.response_category == "GROUNDED_ADVISORY"
    assert res.is_grounded is True
    assert res.abstained is False
    assert res.llm_called is True
    assert len(res.citations) > 0
    assert "pheromone traps" in res.response_text


@pytest.mark.asyncio
async def test_orchestrator_mandi_success(orchestrator_test_db):
    retrieval = RetrievalService(embedding_provider=DeterministicMockEmbeddingProvider(dimension=768))
    orchestrator = AdvisorOrchestrator(
        llm_provider=MockLLMProvider(),
        retrieval=retrieval,
    )

    req = AdvisorQueryRequest(
        query="What is the mandi price of wheat in Indore?",
        language="en-IN",
        farmer_context=FarmerContextDTO(crop="Wheat", state="Madhya Pradesh", district="Indore"),
    )
    res = await orchestrator.answer_query(db=orchestrator_test_db, request=req)

    assert res.intent == "MANDI_PRICE"
    assert res.response_category == "GROUNDED_ADVISORY"
    assert res.is_grounded is True
    assert res.abstained is False
    assert res.data_origin == "production_live"
    assert len(res.citations) > 0


@pytest.mark.asyncio
async def test_orchestrator_unsupported_abstention_no_llm(orchestrator_test_db):
    retrieval = RetrievalService(embedding_provider=DeterministicMockEmbeddingProvider(dimension=768))
    orchestrator = AdvisorOrchestrator(
        llm_provider=MockLLMProvider(),
        retrieval=retrieval,
    )

    req = AdvisorQueryRequest(
        query="Who won the cricket match yesterday?",
        language="en-IN",
    )
    res = await orchestrator.answer_query(db=orchestrator_test_db, request=req)

    assert res.intent == "UNSUPPORTED"
    assert res.response_category == "UNSUPPORTED"
    assert res.abstained is True
    assert res.is_grounded is False
    assert res.llm_called is False  # LLM MUST NOT BE CALLED!
    assert "outside the supported agricultural advisory scope" in res.abstention_reason


@pytest.mark.asyncio
async def test_orchestrator_dragon_fruit_insufficient_evidence_abstention(orchestrator_test_db):
    retrieval = RetrievalService(embedding_provider=DeterministicMockEmbeddingProvider(dimension=768))
    orchestrator = AdvisorOrchestrator(
        llm_provider=MockLLMProvider(),
        retrieval=retrieval,
    )

    req = AdvisorQueryRequest(
        query="What is the recommended treatment for dragon fruit disease in Ladakh?",
        language="en-IN",
    )
    res = await orchestrator.answer_query(db=orchestrator_test_db, request=req)

    assert res.response_category == "INSUFFICIENT_EVIDENCE"
    assert res.abstained is True
    assert res.is_grounded is False
    assert res.llm_called is False  # Must NOT call LLM when evidence is insufficient
    assert len(res.citations) == 0
    assert "verified agricultural information" in res.response_text


# =========================================================================
# Regression Tests for Multi-Turn Persistence & Contextual Resolution
# =========================================================================

@pytest.mark.asyncio
async def test_regression_test_1_turn_1_persistence(orchestrator_test_db):
    """TEST 1: Create conversation -> Turn 1 -> verify DB persistence."""
    retrieval = RetrievalService(embedding_provider=DeterministicMockEmbeddingProvider(dimension=768))
    orchestrator = AdvisorOrchestrator(llm_provider=MockLLMProvider(), retrieval=retrieval)

    conv_id = str(uuid.uuid4())
    req = AdvisorQueryRequest(
        query="What is the wheat price in Indore mandi?",
        language="en-IN",
        conversation_id=conv_id,
    )
    res = await orchestrator.answer_query(db=orchestrator_test_db, request=req)

    assert res.conversation_id == conv_id
    assert res.intent == "MANDI_PRICE"

    # Verify database persistence
    conv = orchestrator_test_db.query(Conversation).filter(Conversation.id == conv_id).first()
    assert conv is not None
    assert conv.id == conv_id
    assert conv.farmer_id is not None

    qlog = orchestrator_test_db.query(QueryLog).filter(QueryLog.conversation_id == conv_id).first()
    assert qlog is not None
    assert qlog.id == res.query_id
    assert qlog.classified_intent == "MANDI_PRICE"
    assert qlog.extracted_entities.get("crop") == "Wheat"
    assert qlog.extracted_entities.get("district") == "Indore"

    rlog = orchestrator_test_db.query(ResponseLog).filter(ResponseLog.query_id == qlog.id).first()
    assert rlog is not None
    assert rlog.is_grounded is True
    assert rlog.response_text == res.response_text


@pytest.mark.asyncio
async def test_regression_test_2_turn_2_context_retrieval(orchestrator_test_db):
    """TEST 2: Same conversation_id -> Turn 2 -> verify previous context retrieved from DB."""
    retrieval = RetrievalService(embedding_provider=DeterministicMockEmbeddingProvider(dimension=768))
    orchestrator = AdvisorOrchestrator(llm_provider=MockLLMProvider(), retrieval=retrieval)

    conv_id = str(uuid.uuid4())
    # Turn 1
    req1 = AdvisorQueryRequest(
        query="What is the wheat price in Indore mandi?",
        language="en-IN",
        conversation_id=conv_id,
    )
    await orchestrator.answer_query(db=orchestrator_test_db, request=req1)

    # Turn 2: Follow-up query omitting crop and district
    req2 = AdvisorQueryRequest(
        query="What is the modal rate today?",
        language="en-IN",
        conversation_id=conv_id,
    )
    res2 = await orchestrator.answer_query(db=orchestrator_test_db, request=req2)

    # Verify context retrieved from DB and inherited
    assert res2.inherited_context.get("crop") == "Wheat"
    assert res2.inherited_context.get("district") == "Indore"
    assert res2.inherited_context.get("state") == "Madhya Pradesh"
    assert res2.extracted_context.get("crop") == "Wheat"
    assert res2.extracted_context.get("district") == "Indore"


@pytest.mark.asyncio
async def test_regression_test_3_wheat_indore_follow_up_tomorrow(orchestrator_test_db):
    """TEST 3: Turn 1: Wheat/Indore -> Turn 2: 'What about tomorrow?' -> inherits Wheat, Indore, MP and resolves MANDI_PRICE."""
    retrieval = RetrievalService(embedding_provider=DeterministicMockEmbeddingProvider(dimension=768))
    orchestrator = AdvisorOrchestrator(llm_provider=MockLLMProvider(), retrieval=retrieval)

    conv_id = str(uuid.uuid4())
    # Turn 1: Wheat price in Indore
    req1 = AdvisorQueryRequest(
        query="What is the wheat price in Indore mandi?",
        language="en-IN",
        conversation_id=conv_id,
    )
    res1 = await orchestrator.answer_query(db=orchestrator_test_db, request=req1)
    assert res1.intent == "MANDI_PRICE"
    assert res1.extracted_context.get("crop") == "Wheat"
    assert res1.extracted_context.get("district") == "Indore"

    # Turn 2: What about tomorrow?
    req2 = AdvisorQueryRequest(
        query="What about tomorrow?",
        language="en-IN",
        conversation_id=conv_id,
    )
    res2 = await orchestrator.answer_query(db=orchestrator_test_db, request=req2)

    assert res2.intent == "MANDI_PRICE"
    assert res2.extracted_context.get("crop") == "Wheat"
    assert res2.extracted_context.get("district") == "Indore"
    assert res2.extracted_context.get("state") == "Madhya Pradesh"
    assert res2.is_grounded is True
    assert res2.abstained is False
    assert res2.data_origin == "production_live"
    assert len(res2.citations) > 0
    assert "Tomorrow's official prices are not published in advance" in res2.response_text


@pytest.mark.asyncio
async def test_regression_test_4_explicit_entities_override_inherited(orchestrator_test_db):
    """TEST 4: Turn 1: Wheat/Indore -> Turn 2: 'What is the tomato price in Tiruppur?' -> explicit Tomato/Tiruppur overrides."""
    retrieval = RetrievalService(embedding_provider=DeterministicMockEmbeddingProvider(dimension=768))
    orchestrator = AdvisorOrchestrator(llm_provider=MockLLMProvider(), retrieval=retrieval)

    conv_id = str(uuid.uuid4())
    # Turn 1: Wheat in Indore
    req1 = AdvisorQueryRequest(
        query="What is the wheat price in Indore mandi?",
        language="en-IN",
        conversation_id=conv_id,
    )
    await orchestrator.answer_query(db=orchestrator_test_db, request=req1)

    # Turn 2: Tomato in Tiruppur
    req2 = AdvisorQueryRequest(
        query="What is the tomato price in Tiruppur?",
        language="en-IN",
        conversation_id=conv_id,
    )
    res2 = await orchestrator.answer_query(db=orchestrator_test_db, request=req2)

    assert res2.extracted_context.get("crop") == "Tomato"
    assert res2.extracted_context.get("district") == "Tiruppur"
    assert res2.extracted_context.get("state") == "Tamil Nadu"
    # Ensure no leakage from Turn 1
    assert res2.extracted_context.get("crop") != "Wheat"
    assert res2.extracted_context.get("district") != "Indore"
    assert res2.inherited_context.get("crop") is None
    assert res2.inherited_context.get("district") is None


@pytest.mark.asyncio
async def test_regression_test_5_explicit_intent_overrides_prior_intent(orchestrator_test_db):
    """TEST 5: Turn 1: Mandi -> Turn 2: 'What about pest control?' -> resolves PEST_DISEASE, does not blindly inherit MANDI_PRICE."""
    retrieval = RetrievalService(embedding_provider=DeterministicMockEmbeddingProvider(dimension=768))
    orchestrator = AdvisorOrchestrator(llm_provider=MockLLMProvider(), retrieval=retrieval)

    conv_id = str(uuid.uuid4())
    # Turn 1: Mandi price
    req1 = AdvisorQueryRequest(
        query="What is the wheat price in Indore mandi?",
        language="en-IN",
        conversation_id=conv_id,
    )
    await orchestrator.answer_query(db=orchestrator_test_db, request=req1)

    # Turn 2: Pest control query
    req2 = AdvisorQueryRequest(
        query="What about pest control for yellow stem borer in paddy?",
        language="en-IN",
        conversation_id=conv_id,
    )
    res2 = await orchestrator.answer_query(db=orchestrator_test_db, request=req2)

    # Must resolve PEST_DISEASE, NOT inherit MANDI_PRICE
    assert res2.intent == "PEST_DISEASE"
    assert res2.response_category == "GROUNDED_ADVISORY"
    assert res2.is_grounded is True


@pytest.mark.asyncio
async def test_regression_test_6_fresh_conversation_unsupported_abstention(orchestrator_test_db):
    """TEST 6: Fresh conversation: 'What about tomorrow?' -> remains UNSUPPORTED / abstained."""
    retrieval = RetrievalService(embedding_provider=DeterministicMockEmbeddingProvider(dimension=768))
    orchestrator = AdvisorOrchestrator(llm_provider=MockLLMProvider(), retrieval=retrieval)

    fresh_conv_id = str(uuid.uuid4())
    req = AdvisorQueryRequest(
        query="What about tomorrow?",
        language="en-IN",
        conversation_id=fresh_conv_id,
    )
    res = await orchestrator.answer_query(db=orchestrator_test_db, request=req)

    assert res.intent == "UNSUPPORTED"
    assert res.response_category == "UNSUPPORTED"
    assert res.abstained is True
    assert res.is_grounded is False
    assert res.llm_called is False


@pytest.mark.asyncio
async def test_regression_test_7_persistence_failure_handling(orchestrator_test_db, monkeypatch, caplog):
    """TEST 7: Persistence failure handling -> error logged with traceback, db.rollback() called, exception propagated."""
    import logging
    from sqlalchemy.exc import SQLAlchemyError
    retrieval = RetrievalService(embedding_provider=DeterministicMockEmbeddingProvider(dimension=768))
    orchestrator = AdvisorOrchestrator(llm_provider=MockLLMProvider(), retrieval=retrieval)

    conv_id = str(uuid.uuid4())
    req = AdvisorQueryRequest(
        query="What is the wheat price in Indore mandi?",
        language="en-IN",
        conversation_id=conv_id,
    )

    # Mock db.commit to raise an exception simulating persistence failure
    def mock_commit():
        raise SQLAlchemyError("Simulated database disk full / connection drop")

    monkeypatch.setattr(orchestrator_test_db, "commit", mock_commit)

    # Rollback spy to ensure rollback is called
    rollback_called = False
    original_rollback = orchestrator_test_db.rollback
    def spy_rollback():
        nonlocal rollback_called
        rollback_called = True
        original_rollback()

    monkeypatch.setattr(orchestrator_test_db, "rollback", spy_rollback)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(SQLAlchemyError) as exc_info:
            await orchestrator.answer_query(db=orchestrator_test_db, request=req)

    assert "Simulated database disk full" in str(exc_info.value)
    assert rollback_called is True
    assert "Failed to persist query/response log to database" in caplog.text

    # Verify no orphan records remain in DB
    orchestrator_test_db.rollback()
    qlogs = orchestrator_test_db.query(QueryLog).filter(QueryLog.conversation_id == conv_id).all()
    assert len(qlogs) == 0


def test_regression_test_8_conversation_history_endpoint_after_turn_1(orchestrator_test_db):
    """TEST 8: Verify GET /api/v1/conversations/{conversation_id} returns persisted conversation after Turn 1."""
    from fastapi.testclient import TestClient
    from backend.app.main import app
    from backend.app.db.session import get_db
    from backend.app.api.v1.advisor import get_orchestrator

    retrieval = RetrievalService(embedding_provider=DeterministicMockEmbeddingProvider(dimension=768))
    orchestrator = AdvisorOrchestrator(llm_provider=MockLLMProvider(), retrieval=retrieval)

    app.dependency_overrides[get_db] = lambda: orchestrator_test_db
    app.dependency_overrides[get_orchestrator] = lambda: orchestrator

    try:
        client = TestClient(app)
        conv_id = str(uuid.uuid4())

        turn1_res = client.post(
            "/api/v1/advisor/query",
            json={
                "query": "What is the wheat price in Indore mandi?",
                "language": "en-IN",
                "conversation_id": conv_id,
            },
        )
        assert turn1_res.status_code == 200

        # Verify GET /api/v1/conversations/{conversation_id}
        hist_res = client.get(f"/api/v1/conversations/{conv_id}")
        assert hist_res.status_code == 200
        hist = hist_res.json()
        assert hist["conversation_id"] == conv_id
        assert hist["total_turns"] == 1
        assert hist["turns"][0]["query_text"] == "What is the wheat price in Indore mandi?"
        assert hist["turns"][0]["classified_intent"] == "MANDI_PRICE"
        assert hist["turns"][0]["is_grounded"] is True
        assert len(hist["turns"][0]["citations"]) > 0
    finally:
        app.dependency_overrides.clear()


def test_regression_test_9_chronological_order_across_multiple_turns(orchestrator_test_db):
    """TEST 9: Verify multiple turns in same conversation remain ordered chronologically."""
    from fastapi.testclient import TestClient
    from backend.app.main import app
    from backend.app.db.session import get_db
    from backend.app.api.v1.advisor import get_orchestrator

    retrieval = RetrievalService(embedding_provider=DeterministicMockEmbeddingProvider(dimension=768))
    orchestrator = AdvisorOrchestrator(llm_provider=MockLLMProvider(), retrieval=retrieval)

    app.dependency_overrides[get_db] = lambda: orchestrator_test_db
    app.dependency_overrides[get_orchestrator] = lambda: orchestrator

    try:
        client = TestClient(app)
        conv_id = str(uuid.uuid4())

        queries = [
            "What is the wheat price in Indore mandi?",
            "What about tomorrow?",
            "How to control yellow stem borer in paddy?",
        ]

        for q in queries:
            res = client.post(
                "/api/v1/advisor/query",
                json={
                    "query": q,
                    "language": "en-IN",
                    "conversation_id": conv_id,
                },
            )
            assert res.status_code == 200

        hist_res = client.get(f"/api/v1/conversations/{conv_id}")
        assert hist_res.status_code == 200
        hist = hist_res.json()
        assert hist["conversation_id"] == conv_id
        assert hist["total_turns"] == 3

        assert hist["turns"][0]["query_text"] == queries[0]
        assert hist["turns"][1]["query_text"] == queries[1]
        assert hist["turns"][2]["query_text"] == queries[2]

        # Verify chronological ascending order
        t0 = hist["turns"][0]["created_at"]
        t1 = hist["turns"][1]["created_at"]
        t2 = hist["turns"][2]["created_at"]
        assert t0 <= t1 <= t2
    finally:
        app.dependency_overrides.clear()


# =========================================================================
# UUID Validation & Rejection Regression Tests (Audit Section F)
# =========================================================================

def test_uuid_audit_1_valid_uuid_accepted_unchanged(orchestrator_test_db):
    """1. Valid UUID accepted unchanged without modification."""
    from fastapi.testclient import TestClient
    from backend.app.main import app
    from backend.app.db.session import get_db
    from backend.app.api.v1.advisor import get_orchestrator

    retrieval = RetrievalService(embedding_provider=DeterministicMockEmbeddingProvider(dimension=768))
    orchestrator = AdvisorOrchestrator(llm_provider=MockLLMProvider(), retrieval=retrieval)

    app.dependency_overrides[get_db] = lambda: orchestrator_test_db
    app.dependency_overrides[get_orchestrator] = lambda: orchestrator

    try:
        client = TestClient(app)
        valid_uuid = "550e8400-e29b-41d4-a716-446655440000"
        res = client.post(
            "/api/v1/advisor/query",
            json={
                "query": "What is the wheat price in Indore mandi?",
                "language": "en-IN",
                "conversation_id": valid_uuid,
            },
        )
        assert res.status_code == 200
        assert res.json()["conversation_id"] == valid_uuid
    finally:
        app.dependency_overrides.clear()


def test_uuid_audit_2_invalid_conversation_id_rejected_cleanly(orchestrator_test_db):
    """2. Invalid conversation_id rejected cleanly with HTTP 422 validation error."""
    from fastapi.testclient import TestClient
    from backend.app.main import app
    from backend.app.db.session import get_db
    from backend.app.api.v1.advisor import get_orchestrator

    retrieval = RetrievalService(embedding_provider=DeterministicMockEmbeddingProvider(dimension=768))
    orchestrator = AdvisorOrchestrator(llm_provider=MockLLMProvider(), retrieval=retrieval)

    app.dependency_overrides[get_db] = lambda: orchestrator_test_db
    app.dependency_overrides[get_orchestrator] = lambda: orchestrator

    try:
        client = TestClient(app)
        invalid_ids = ["not-a-uuid", "12345", "test_conv_id", "invalid-uuid-format-xxxx", "undefined", "[object Object]"]
        for bad_id in invalid_ids:
            res = client.post(
                "/api/v1/advisor/query",
                json={
                    "query": "What is the wheat price in Indore mandi?",
                    "language": "en-IN",
                    "conversation_id": bad_id,
                },
            )
            assert res.status_code == 422, f"Expected 422 for invalid ID '{bad_id}', got {res.status_code}"
            assert "Invalid conversation_id" in str(res.json())
    finally:
        app.dependency_overrides.clear()


def test_uuid_audit_3_server_generated_conversation_id_is_valid_uuid(orchestrator_test_db):
    """3. Server-generated conversation ID is a valid UUID."""
    from fastapi.testclient import TestClient
    from backend.app.main import app
    from backend.app.db.session import get_db
    from backend.app.api.v1.advisor import get_orchestrator

    retrieval = RetrievalService(embedding_provider=DeterministicMockEmbeddingProvider(dimension=768))
    orchestrator = AdvisorOrchestrator(llm_provider=MockLLMProvider(), retrieval=retrieval)

    app.dependency_overrides[get_db] = lambda: orchestrator_test_db
    app.dependency_overrides[get_orchestrator] = lambda: orchestrator

    try:
        client = TestClient(app)
        # Omit conversation_id
        res = client.post(
            "/api/v1/advisor/query",
            json={
                "query": "What is the wheat price in Indore mandi?",
                "language": "en-IN",
            },
        )
        assert res.status_code == 200
        gen_id = res.json()["conversation_id"]
        assert gen_id is not None
        # Verify it parses as valid UUID
        parsed = uuid.UUID(gen_id)
        assert str(parsed) == gen_id
        assert parsed.version == 4
    finally:
        app.dependency_overrides.clear()


def test_uuid_audit_4_same_valid_conversation_id_persists_and_retrieves_correctly(orchestrator_test_db):
    """4. Same valid conversation_id persists and retrieves correctly across multiple turns."""
    from fastapi.testclient import TestClient
    from backend.app.main import app
    from backend.app.db.session import get_db
    from backend.app.api.v1.advisor import get_orchestrator

    retrieval = RetrievalService(embedding_provider=DeterministicMockEmbeddingProvider(dimension=768))
    orchestrator = AdvisorOrchestrator(llm_provider=MockLLMProvider(), retrieval=retrieval)

    app.dependency_overrides[get_db] = lambda: orchestrator_test_db
    app.dependency_overrides[get_orchestrator] = lambda: orchestrator

    try:
        client = TestClient(app)
        conv_id = str(uuid.uuid4())

        # Turn 1
        res1 = client.post(
            "/api/v1/advisor/query",
            json={
                "query": "What is the wheat price in Indore mandi?",
                "language": "en-IN",
                "conversation_id": conv_id,
            },
        )
        assert res1.status_code == 200
        assert res1.json()["conversation_id"] == conv_id

        # Turn 2
        res2 = client.post(
            "/api/v1/advisor/query",
            json={
                "query": "What about tomorrow?",
                "language": "en-IN",
                "conversation_id": conv_id,
            },
        )
        assert res2.status_code == 200
        assert res2.json()["conversation_id"] == conv_id

        # Retrieve conversation
        hist_res = client.get(f"/api/v1/conversations/{conv_id}")
        assert hist_res.status_code == 200
        hist = hist_res.json()
        assert hist["conversation_id"] == conv_id
        assert hist["total_turns"] == 2
        assert hist["turns"][0]["query_text"] == "What is the wheat price in Indore mandi?"
        assert hist["turns"][1]["query_text"] == "What about tomorrow?"
    finally:
        app.dependency_overrides.clear()


def test_uuid_audit_5_get_conversation_invalid_id_returns_clean_400(orchestrator_test_db):
    """5. GET /conversations/{id} with invalid ID returns clean 400 response without database exception."""
    from fastapi.testclient import TestClient
    from backend.app.main import app
    from backend.app.db.session import get_db
    from backend.app.api.v1.advisor import get_orchestrator

    retrieval = RetrievalService(embedding_provider=DeterministicMockEmbeddingProvider(dimension=768))
    orchestrator = AdvisorOrchestrator(llm_provider=MockLLMProvider(), retrieval=retrieval)

    app.dependency_overrides[get_db] = lambda: orchestrator_test_db
    app.dependency_overrides[get_orchestrator] = lambda: orchestrator

    try:
        client = TestClient(app)
        invalid_ids = ["not-a-uuid", "12345", "drop-table", "conv-999-bad", "undefined", "[object Object]"]
        for bad_id in invalid_ids:
            res = client.get(f"/api/v1/conversations/{bad_id}")
            assert res.status_code == 400, f"Expected 400 for '{bad_id}', got {res.status_code}"
            assert res.json()["detail"]["error_code"] == "INVALID_CONVERSATION_ID"

            # Check under advisor router namespace as well
            res_adv = client.get(f"/api/v1/advisor/conversations/{bad_id}")
            assert res_adv.status_code == 400
            assert res_adv.json()["detail"]["error_code"] == "INVALID_CONVERSATION_ID"
    finally:
        app.dependency_overrides.clear()


def test_end_to_end_production_flow_and_session_recovery(orchestrator_test_db):
    """End-to-end verification of production flow: session recovery, multi-turn inheritance, future date clarification, and explicit override."""
    from fastapi.testclient import TestClient
    from backend.app.main import app
    from backend.app.db.session import get_db
    from backend.app.api.v1.advisor import get_orchestrator

    retrieval = RetrievalService(embedding_provider=DeterministicMockEmbeddingProvider(dimension=768))
    orchestrator = AdvisorOrchestrator(llm_provider=MockLLMProvider(), retrieval=retrieval)

    app.dependency_overrides[get_db] = lambda: orchestrator_test_db
    app.dependency_overrides[get_orchestrator] = lambda: orchestrator

    try:
        client = TestClient(app)

        # 1. Corrupted session value: "[object Object]" is rejected cleanly at boundary (no 500, no DB error)
        corrupted_res = client.post(
            "/api/v1/advisor/query",
            json={
                "query": "What is the wheat price in Indore mandi?",
                "language": "en-IN",
                "conversation_id": "[object Object]",
            },
        )
        assert corrupted_res.status_code == 422
        assert "Invalid conversation_id" in str(corrupted_res.json())

        # 2. Empty string recovery: empty string is treated as new conversation
        empty_res = client.post(
            "/api/v1/advisor/query",
            json={
                "query": "What is the wheat price in Indore mandi?",
                "language": "en-IN",
                "conversation_id": "",
            },
        )
        assert empty_res.status_code == 200
        recovered_id = empty_res.json()["conversation_id"]
        assert recovered_id is not None
        assert uuid.UUID(recovered_id)

        # 3. Turn 1: "What is the wheat price in Indore mandi?"
        conv_id = str(uuid.uuid4())
        turn1_res = client.post(
            "/api/v1/advisor/query",
            json={
                "query": "What is the wheat price in Indore mandi?",
                "language": "en-IN",
                "conversation_id": conv_id,
            },
        )
        assert turn1_res.status_code == 200
        data1 = turn1_res.json()
        assert data1["conversation_id"] == conv_id
        assert data1["intent"] == "MANDI_PRICE"
        assert data1["extracted_context"]["crop"] == "Wheat"
        assert data1["extracted_context"]["district"] == "Indore"

        # Verify Turn 1 is persisted
        hist1 = client.get(f"/api/v1/conversations/{conv_id}").json()
        assert hist1["total_turns"] == 1
        assert hist1["turns"][0]["query_text"] == "What is the wheat price in Indore mandi?"

        # 4. Turn 2: "What about tomorrow?" using same conversation_id
        turn2_res = client.post(
            "/api/v1/advisor/query",
            json={
                "query": "What about tomorrow?",
                "language": "en-IN",
                "conversation_id": conv_id,
            },
        )
        assert turn2_res.status_code == 200
        data2 = turn2_res.json()
        assert data2["conversation_id"] == conv_id
        assert data2["intent"] == "MANDI_PRICE"
        assert data2["extracted_context"]["crop"] == "Wheat"
        assert data2["extracted_context"]["district"] == "Indore"
        assert data2["extracted_context"]["state"] == "Madhya Pradesh"
        assert data2["is_grounded"] is True
        assert data2["abstained"] is False
        assert "Tomorrow's official prices are not published in advance" in data2["response_text"]
        assert "Displaying the latest verified daily arrival data" in data2["response_text"]

        # Verify Turn 2 is persisted
        hist2 = client.get(f"/api/v1/conversations/{conv_id}").json()
        assert hist2["total_turns"] == 2
        assert hist2["turns"][1]["query_text"] == "What about tomorrow?"

        # 5. Explicit Override: "What is the tomato price in Tiruppur?"
        turn3_res = client.post(
            "/api/v1/advisor/query",
            json={
                "query": "What is the tomato price in Tiruppur?",
                "language": "en-IN",
                "conversation_id": conv_id,
            },
        )
        assert turn3_res.status_code == 200
        data3 = turn3_res.json()
        assert data3["extracted_context"]["crop"] == "Tomato"
        assert data3["extracted_context"]["district"] == "Tiruppur"
        assert data3["extracted_context"]["state"] == "Tamil Nadu"
        # Verify no leakage from prior turns
        assert data3["extracted_context"]["crop"] != "Wheat"
        assert data3["extracted_context"]["district"] != "Indore"
        assert data3["inherited_context"].get("crop") is None
        assert data3["inherited_context"].get("district") is None

        # Verify Turn 3 is persisted
        hist3 = client.get(f"/api/v1/conversations/{conv_id}").json()
        assert hist3["total_turns"] == 3
        assert hist3["turns"][2]["query_text"] == "What is the tomato price in Tiruppur?"
    finally:
        app.dependency_overrides.clear()
