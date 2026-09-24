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
from backend.app.schemas.advisor import AgriculturalIntent, FarmerContextDTO
from backend.app.services.retrieval_service import RetrievalService
from backend.app.providers.embedding_provider import DeterministicMockEmbeddingProvider


@pytest.fixture
def test_db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    # Seed 1 source doc and 2 chunks with 768-dim embeddings
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
    vec1 = embedder.generate_embedding_sync("Yellow stem borer management in paddy using pheromone traps.")
    vec2 = embedder.generate_embedding_sync("Wheat production technology and fertilizer schedule.")

    c1 = KnowledgeChunk(
        id=str(uuid.uuid4()),
        document_id=doc.id,
        chunk_index=0,
        crop_name="Paddy",
        topic="Pest Management",
        content="Yellow stem borer management in paddy: Install pheromone traps at 20 traps/ha.",
        content_hash="hash1",
        token_count=15,
        embedding=vec1,
    )
    c2 = KnowledgeChunk(
        id=str(uuid.uuid4()),
        document_id=doc.id,
        chunk_index=1,
        crop_name="Wheat",
        topic="Fertilizer",
        content="Wheat fertilizer schedule: Apply 120 kg N, 60 kg P2O5, and 40 kg K2O per hectare.",
        content_hash="hash2",
        token_count=20,
        embedding=vec2,
    )
    db.add_all([c1, c2])

    # Seed 1 scheme
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

    # Seed mandi prices: one production_live, one development_seed
    mandi_live = MandiPrice(
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
    mandi_mock = MandiPrice(
        id=str(uuid.uuid4()),
        state="Madhya Pradesh",
        district="Bhopal",
        market="Bhopal",
        commodity="Wheat",
        variety="Common",
        grade="FAQ",
        arrival_date=date(2026, 9, 22),
        min_price=2000.0,
        max_price=2200.0,
        modal_price=2100.0,
        source="TestMock",
        data_origin="development_seed",
    )
    db.add_all([mandi_live, mandi_mock])
    db.commit()

    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.mark.asyncio
async def test_agricultural_vector_retrieval(test_db_session):
    retriever = RetrievalService(embedding_provider=DeterministicMockEmbeddingProvider(dimension=768))
    ctx = FarmerContextDTO(crop="Paddy", pest_disease="Yellow stem borer")
    evidence = await retriever.retrieve(
        db=test_db_session,
        query="Yellow stem borer management in paddy",
        intent=AgriculturalIntent.PEST_DISEASE,
        context=ctx,
    )

    assert len(evidence) > 0
    top = evidence[0]
    assert "pheromone traps" in top.content
    assert top.issuing_authority == "ICAR - Indian Institute of Rice Research"
    assert top.data_origin == "production_cached"


@pytest.mark.asyncio
async def test_government_scheme_retrieval(test_db_session):
    retriever = RetrievalService(embedding_provider=DeterministicMockEmbeddingProvider(dimension=768))
    evidence = await retriever.retrieve(
        db=test_db_session,
        query="Tell me about PM-KISAN benefits",
        intent=AgriculturalIntent.GOVERNMENT_SCHEME,
    )

    assert len(evidence) > 0
    assert "PM_KISAN" in evidence[0].metadata.get("scheme_code")
    assert "pmkisan.gov.in" in evidence[0].official_url


@pytest.mark.asyncio
async def test_mandi_price_retrieval_rejection_of_development_seed(test_db_session):
    retriever = RetrievalService(embedding_provider=DeterministicMockEmbeddingProvider(dimension=768))

    # Query for Indore (has production_live record)
    ctx_indore = FarmerContextDTO(crop="Wheat", state="Madhya Pradesh", district="Indore")
    evidence_indore = await retriever.retrieve(
        db=test_db_session,
        query="Wheat price in Indore",
        intent=AgriculturalIntent.MANDI_PRICE,
        context=ctx_indore,
    )
    assert len(evidence_indore) == 1
    assert evidence_indore[0].data_origin == "production_live"
    assert evidence_indore[0].metadata["modal_price"] == 2650.0

    # Query for Bhopal (only has development_seed record -> MUST BE REJECTED)
    ctx_bhopal = FarmerContextDTO(crop="Wheat", state="Madhya Pradesh", district="Bhopal")
    evidence_bhopal = await retriever.retrieve(
        db=test_db_session,
        query="Wheat price in Bhopal",
        intent=AgriculturalIntent.MANDI_PRICE,
        context=ctx_bhopal,
    )
    # development_seed is strictly filtered out
    assert len(evidence_bhopal) == 0


def test_retrieval_score_semantics_deterministic():
    from backend.app.services.retrieval_service import cosine_similarity

    # 1. Identical vectors must yield exact 1.0000
    v1 = [0.6, 0.8]
    assert round(cosine_similarity(v1, v1), 4) == 1.0000

    # 2. Orthogonal vectors must yield exact 0.0000
    v_orth1 = [1.0, 0.0]
    v_orth2 = [0.0, 1.0]
    assert round(cosine_similarity(v_orth1, v_orth2), 4) == 0.0000

    # 3. Opposite vectors must yield exact -1.0000
    v_opp1 = [1.0, 0.0]
    v_opp2 = [-1.0, 0.0]
    assert round(cosine_similarity(v_opp1, v_opp2), 4) == -1.0000

    # 4. Vector with known angle (e.g. 45 degrees: cos(45) = 1/sqrt(2) approx 0.7071)
    v_45_a = [1.0, 0.0]
    v_45_b = [1.0, 1.0]
    sim_45 = cosine_similarity(v_45_a, v_45_b)
    assert round(sim_45, 4) == 0.7071

    # 5. Empty or mismatched dimensions yield 0.0
    assert cosine_similarity([], [1.0]) == 0.0
    assert cosine_similarity([1.0], [1.0, 2.0]) == 0.0


@pytest.mark.asyncio
async def test_unrepresented_crop_retrieval_isolation(test_db_session):
    """
    Guarantees that when a farmer queries an unrepresented crop (e.g. Dragon fruit),
    the system does NOT fall back to other crops (e.g. Paddy or Wheat) and returns 0 items,
    forcing safe abstention.
    """
    retriever = RetrievalService(embedding_provider=DeterministicMockEmbeddingProvider(dimension=768))
    ctx = FarmerContextDTO(crop="Dragon fruit", state="Ladakh")
    evidence = await retriever.retrieve(
        db=test_db_session,
        query="What is the recommended treatment for dragon fruit disease in Ladakh?",
        intent=AgriculturalIntent.PEST_DISEASE,
        context=ctx,
    )

    # Must return 0 evidence items because no dragon fruit chunks exist
    assert len(evidence) == 0
