import pytest
import uuid
from datetime import date
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.main import app
from backend.app.db.session import Base, get_db
from backend.app.models.models import MandiPrice, SourceDocument, KnowledgeChunk
from backend.app.schemas.advisor import AgriculturalIntent, AdvisorQueryRequest
from backend.app.services.intent_classifier import intent_classifier
from backend.app.services.grounding_validator import grounding_validator
from backend.app.providers.embedding_provider import DeterministicMockEmbeddingProvider
from backend.app.providers.llm_provider import MockLLMProvider
from backend.app.services.retrieval_service import RetrievalService
from backend.app.services.advisor_orchestrator import AdvisorOrchestrator


@pytest.fixture
def auth_test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

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

    # Seed 1 source doc and 1 chunk for general advisory
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
    db.commit()

    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def auth_client(auth_test_db):
    def override_get_db():
        try:
            yield auth_test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ==============================================================================
# CASE 2 & CASE 3: Regional Language Mandi Price Queries
# ==============================================================================

@pytest.mark.asyncio
async def test_case_2_tamil_mandi_query(auth_test_db):
    """CASE 2: 'இந்தூரில் கோதுமை விலை என்ன?' -> Grounded Tamil Mandi response."""
    retrieval = RetrievalService(embedding_provider=DeterministicMockEmbeddingProvider(dimension=768))
    orchestrator = AdvisorOrchestrator(llm_provider=MockLLMProvider(), retrieval=retrieval)

    req = AdvisorQueryRequest(
        query="இந்தூரில் கோதுமை விலை என்ன?",
        language="ta-IN",
    )
    res = await orchestrator.answer_query(db=auth_test_db, request=req)

    assert res.intent == "MANDI_PRICE"
    assert res.extracted_context.get("crop") == "Wheat"
    assert res.extracted_context.get("district") == "Indore"
    assert res.extracted_context.get("state") == "Madhya Pradesh"
    assert res.is_grounded is True
    assert res.abstained is False
    assert res.data_origin == "production_live"
    # Response must be in Tamil
    assert "சரிபார்க்கப்பட்ட சந்தை விலை" in res.response_text
    assert "குறைந்தபட்ச விலை" in res.response_text
    assert "2650" in res.response_text


@pytest.mark.asyncio
async def test_case_3_hindi_mandi_query(auth_test_db):
    """CASE 3: 'इंदौर में गेहूं का भाव क्या है?' -> Grounded Hindi Mandi response."""
    retrieval = RetrievalService(embedding_provider=DeterministicMockEmbeddingProvider(dimension=768))
    orchestrator = AdvisorOrchestrator(llm_provider=MockLLMProvider(), retrieval=retrieval)

    req = AdvisorQueryRequest(
        query="इंदौर में गेहूं का भाव क्या है?",
        language="hi-IN",
    )
    res = await orchestrator.answer_query(db=auth_test_db, request=req)

    assert res.intent == "MANDI_PRICE"
    assert res.extracted_context.get("crop") == "Wheat"
    assert res.extracted_context.get("district") == "Indore"
    assert res.extracted_context.get("state") == "Madhya Pradesh"
    assert res.is_grounded is True
    assert res.abstained is False
    assert res.data_origin == "production_live"
    # Response must be in Hindi
    assert "सत्यापित मंडी भाव" in res.response_text
    assert "मॉडल (औसत) भाव" in res.response_text
    assert "2650" in res.response_text


# ==============================================================================
# Expanded Agricultural Intents
# ==============================================================================

def test_expanded_agricultural_intents_classification():
    """Verifies that all 11 new/broader agricultural intents are properly classified."""
    cases = [
        ("Which fertilizer should I apply for tomato?", AgriculturalIntent.FERTILIZER),
        ("What is the best drip irrigation schedule for sugarcane?", AgriculturalIntent.IRRIGATION),
        ("How to select certified hybrid seeds for cotton?", AgriculturalIntent.SEED_SELECTION),
        ("What is the seed treatment procedure with fungicide?", AgriculturalIntent.SEED_TREATMENT),
        ("How to do soil testing and improve soil health?", AgriculturalIntent.SOIL_MANAGEMENT),
        ("How to control weeds and use herbicide in paddy?", AgriculturalIntent.WEED_MANAGEMENT),
        ("How to apply for PM Fasal Bima crop insurance?", AgriculturalIntent.CROP_INSURANCE),
        ("How to apply for Kisan Credit Card crop loan?", AgriculturalIntent.AGRICULTURAL_CREDIT),
        ("What is the right time for harvesting wheat?", AgriculturalIntent.HARVESTING),
        ("How to dry and sort grains post harvest?", AgriculturalIntent.POST_HARVEST),
        ("How to store wheat grains safely in warehouse?", AgriculturalIntent.STORAGE),
    ]

    for q, expected_intent in cases:
        intent, conf = intent_classifier.classify(q)
        assert intent == expected_intent, f"Query '{q}' was classified as {intent}, expected {expected_intent}"
        assert conf >= 0.85


# ==============================================================================
# CASE 8: Safe Abstention & Out-of-Scope Queries
# ==============================================================================

def test_all_11_languages_abstention_text():
    """Verifies that safe abstention messages exist in all 11 supported languages."""
    languages = [
        "hi-IN", "te-IN", "ta-IN", "mr-IN", "kn-IN",
        "bn-IN", "gu-IN", "ml-IN", "pa-IN", "od-IN", "en-IN"
    ]
    for lang in languages:
        text = grounding_validator.get_abstention_text(language=lang)
        assert text is not None and len(text) > 10, f"Abstention text for {lang} is empty"


@pytest.mark.asyncio
async def test_case_8_out_of_scope_abstention(auth_test_db):
    """CASE 8: Out-of-scope query safely abstains without LLM or hallucinations."""
    retrieval = RetrievalService(embedding_provider=DeterministicMockEmbeddingProvider(dimension=768))
    orchestrator = AdvisorOrchestrator(llm_provider=MockLLMProvider(), retrieval=retrieval)

    req = AdvisorQueryRequest(
        query="Who won the cricket match between India and Australia yesterday?",
        language="hi-IN",
    )
    res = await orchestrator.answer_query(db=auth_test_db, request=req)

    assert res.intent == "UNSUPPORTED"
    assert res.abstained is True
    assert res.is_grounded is False
    assert res.llm_called is False
    assert "सुरक्षित उत्तर देने के लिए" in res.response_text


# ==============================================================================
# CASE 9: User A vs User B Authorization & Conversation History
# ==============================================================================

def test_case_9_user_authorization_ownership(auth_client):
    """
    CASE 9: Server-enforced conversation authorization:
    - User A creates conversation
    - User A accesses conversation -> 200 OK
    - User B attempts to access User A's conversation -> 403 Forbidden
    - User B attempts to query into User A's conversation -> 403 Forbidden
    """
    conv_id = str(uuid.uuid4())

    # 1. User A queries and creates conversation
    res_a = auth_client.post(
        "/api/v1/advisor/query",
        json={
            "query": "What is the wheat price in Indore?",
            "language": "en-IN",
            "conversation_id": conv_id,
        },
        headers={"Authorization": "Bearer test-user-a"},
    )
    assert res_a.status_code == 200
    assert res_a.json()["conversation_id"] == conv_id

    # 2. User A fetches conversation history -> 200 OK
    res_get_a = auth_client.get(
        f"/api/v1/conversations/{conv_id}",
        headers={"Authorization": "Bearer test-user-a"},
    )
    assert res_get_a.status_code == 200
    assert res_get_a.json()["conversation_id"] == conv_id
    assert res_get_a.json()["total_turns"] == 1

    # 3. User B attempts to fetch User A's conversation -> 403 Forbidden
    res_get_b = auth_client.get(
        f"/api/v1/conversations/{conv_id}",
        headers={"Authorization": "Bearer test-user-b"},
    )
    assert res_get_b.status_code == 403
    assert res_get_b.json()["detail"]["error_code"] == "FORBIDDEN"

    # 4. User B attempts to query into User A's conversation -> 403 Forbidden
    res_query_b = auth_client.post(
        "/api/v1/advisor/query",
        json={
            "query": "What about tomorrow?",
            "language": "en-IN",
            "conversation_id": conv_id,
        },
        headers={"Authorization": "Bearer test-user-b"},
    )
    assert res_query_b.status_code == 403

    # 5. User A lists their conversations -> sees conv_id
    res_list_a = auth_client.get(
        "/api/v1/conversations",
        headers={"Authorization": "Bearer test-user-a"},
    )
    assert res_list_a.status_code == 200
    conv_ids_a = [c["id"] for c in res_list_a.json()["conversations"]]
    assert conv_id in conv_ids_a

    # 6. User B lists their conversations -> does NOT see conv_id
    res_list_b = auth_client.get(
        "/api/v1/conversations",
        headers={"Authorization": "Bearer test-user-b"},
    )
    assert res_list_b.status_code == 200
    conv_ids_b = [c["id"] for c in res_list_b.json()["conversations"]]
    assert conv_id not in conv_ids_b

    # 7. User B attempts to delete User A's conversation -> 403 Forbidden
    res_del_b = auth_client.delete(
        f"/api/v1/conversations/{conv_id}",
        headers={"Authorization": "Bearer test-user-b"},
    )
    assert res_del_b.status_code == 403

    # 8. User A deletes their conversation -> 200 OK
    res_del_a = auth_client.delete(
        f"/api/v1/conversations/{conv_id}",
        headers={"Authorization": "Bearer test-user-a"},
    )
    assert res_del_a.status_code == 200


# ==============================================================================
# CASE 10: Malformed Conversation ID Rejection
# ==============================================================================

def test_case_10_malformed_conversation_id(auth_client):
    """CASE 10: Malformed or invalid conversation_id values are rejected with 422 or 400."""
    # 1. Non-UUID string in POST query
    res = auth_client.post(
        "/api/v1/advisor/query",
        json={
            "query": "What is the wheat price in Indore?",
            "language": "en-IN",
            "conversation_id": "malformed-not-a-uuid",
        },
    )
    assert res.status_code == 422

    # 2. Corrupted "[object Object]"
    res2 = auth_client.post(
        "/api/v1/advisor/query",
        json={
            "query": "What is the wheat price in Indore?",
            "language": "en-IN",
            "conversation_id": "[object Object]",
        },
    )
    assert res2.status_code == 422

    # 3. Malformed UUID in GET conversations
    res3 = auth_client.get("/api/v1/conversations/not-a-uuid")
    assert res3.status_code == 400
    assert res3.json()["detail"]["error_code"] == "INVALID_CONVERSATION_ID"
