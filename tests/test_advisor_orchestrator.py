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
    vec = embedder.generate_embedding_sync("Yellow stem borer management in paddy: Install pheromone traps.")
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

    # Seed Mandi price
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
