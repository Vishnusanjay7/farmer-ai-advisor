import pytest
import uuid
from datetime import date
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.main import app
from backend.app.db.session import Base, get_db
from backend.app.api.v1.advisor import get_orchestrator
from backend.app.services.advisor_orchestrator import AdvisorOrchestrator
from backend.app.services.retrieval_service import RetrievalService
from backend.app.providers.embedding_provider import DeterministicMockEmbeddingProvider
from backend.app.providers.llm_provider import MockLLMProvider
from backend.app.models.models import SourceDocument, KnowledgeChunk


@pytest.fixture
def api_test_db():
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
        content_hash="hash_api_1",
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


def test_advisor_api_success(api_test_db):
    test_retrieval = RetrievalService(embedding_provider=DeterministicMockEmbeddingProvider(dimension=768))
    test_orchestrator = AdvisorOrchestrator(
        llm_provider=MockLLMProvider(),
        retrieval=test_retrieval,
    )

    app.dependency_overrides[get_db] = lambda: api_test_db
    app.dependency_overrides[get_orchestrator] = lambda: test_orchestrator

    client = TestClient(app)
    response = client.post(
        "/api/v1/advisor/query",
        json={
            "query": "How do I control yellow stem borer in paddy?",
            "language": "en-IN",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "PEST_DISEASE"
    assert data["is_grounded"] is True
    assert data["abstained"] is False
    assert len(data["citations"]) > 0
    assert "pheromone traps" in data["response_text"]

    app.dependency_overrides.clear()


def test_advisor_api_unsupported_abstention(api_test_db):
    test_retrieval = RetrievalService(embedding_provider=DeterministicMockEmbeddingProvider(dimension=768))
    test_orchestrator = AdvisorOrchestrator(
        llm_provider=MockLLMProvider(),
        retrieval=test_retrieval,
    )

    app.dependency_overrides[get_db] = lambda: api_test_db
    app.dependency_overrides[get_orchestrator] = lambda: test_orchestrator

    client = TestClient(app)
    response = client.post(
        "/api/v1/advisor/query",
        json={
            "query": "Who is the president of France?",
            "language": "en-IN",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "UNSUPPORTED"
    assert data["abstained"] is True
    assert data["is_grounded"] is False
    assert data["llm_called"] is False

    app.dependency_overrides.clear()


def test_advisor_api_empty_query_validation():
    client = TestClient(app)
    response = client.post(
        "/api/v1/advisor/query",
        json={
            "query": "",
            "language": "en-IN",
        },
    )
    assert response.status_code == 422
