import pytest
import uuid
from datetime import date
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.main import app
from backend.app.db.session import Base, get_db
from backend.app.api.v1.advisor import get_orchestrator
from backend.app.providers.llm_provider import GeminiLLMProvider
from backend.app.models.models import MandiPrice
from backend.app.services.retrieval_service import RetrievalService
from backend.app.providers.embedding_provider import DeterministicMockEmbeddingProvider
from backend.app.schemas.advisor import AgriculturalIntent, FarmerContextDTO


@pytest.fixture
def db_session():
    """Isolated in-memory database session fixture."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


# =============================================================================
# Test 1: Sanitized Advisor Exception Handling (RFC7807)
# =============================================================================
def test_advisor_exception_is_sanitized():
    """
    Verifies that internal backend/database/provider exceptions are never leaked
    to the client and instead return a sanitized RFC7807 response.
    """
    failing_orchestrator = MagicMock()
    failing_orchestrator.answer_query = AsyncMock(
        side_effect=RuntimeError("psycopg2.OperationalError: could not connect to server: Connection refused (postgresql://postgres:secret_pass@db.supabase.co:5432/postgres)")
    )

    app.dependency_overrides[get_orchestrator] = lambda: failing_orchestrator
    client = TestClient(app)

    try:
        response = client.post(
            "/api/v1/advisor/query",
            json={"query": "How to treat yellow rust?", "language": "en-IN"},
        )

        assert response.status_code == 500
        data = response.json()

        # Must have sanitized RFC7807 structure
        assert "detail" in data
        detail = data["detail"]
        assert isinstance(detail, dict)
        assert detail.get("error_code") == "ADVISOR_PROCESSING_ERROR"
        assert "temporary error" in detail.get("message", "")

        # Strict assertion: NO sensitive tokens leaked
        response_str = str(data)
        assert "postgres" not in response_str
        assert "secret_pass" not in response_str
        assert "psycopg2" not in response_str
        assert "Connection refused" not in response_str
        assert "Traceback" not in response_str
    finally:
        app.dependency_overrides.clear()


# =============================================================================
# Test 2: Gemini API Key Transmitted via Header (x-goog-api-key)
# =============================================================================
@pytest.mark.asyncio
async def test_gemini_key_header_transmission():
    """
    Verifies that GeminiLLMProvider transmits the API key in the 'x-goog-api-key'
    HTTP header and NOT in the URL query string.
    """
    provider = GeminiLLMProvider(api_key="test-gemini-key-12345", model="gemini-3.8-flash")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "Irrigate wheat at CRI stage."}]
                }
            }
        ]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        res = await provider.generate_grounded_response(
            system_prompt="Agricultural assistant",
            user_query="When to irrigate wheat?",
            context_chunks=["Irrigate wheat at Crown Root Initiation."],
            farmer_context={"language": "en-IN"},
        )

        assert res.is_grounded is True
        assert "Irrigate wheat" in res.answer_text

        # Verify call arguments
        mock_post.assert_called_once()
        call_args, call_kwargs = mock_post.call_args

        called_url = call_args[0]
        # Assert key is NOT in query string
        assert "key=" not in called_url
        assert "test-gemini-key-12345" not in called_url

        # Assert key IS in headers
        headers = call_kwargs.get("headers", {})
        assert headers.get("x-goog-api-key") == "test-gemini-key-12345"
        assert headers.get("Content-Type") == "application/json"


# =============================================================================
# Test 3: development_seed Data is NEVER Returned as Authoritative
# =============================================================================
@pytest.mark.asyncio
async def test_development_seed_never_authoritative(db_session):
    """
    Verifies that development_seed mandi records are strictly excluded by the
    retrieval service and never presented to farmers as verified advice.
    """
    # Insert a development_seed record
    seed_record = MandiPrice(
        id=str(uuid.uuid4()),
        state="Punjab",
        district="Ludhiana",
        market="Khanna",
        commodity="Wheat",
        variety="Kalyansona",
        grade="FAQ",
        arrival_date=date(2026, 9, 20),
        min_price=2200.0,
        max_price=2400.0,
        modal_price=2300.0,
        source="Test Seed Script",
        data_origin="development_seed",
    )
    db_session.add(seed_record)
    db_session.commit()

    retriever = RetrievalService(embedding_provider=DeterministicMockEmbeddingProvider(dimension=768))

    # Query for Khanna market where only development_seed exists
    ctx = FarmerContextDTO(crop="Wheat", state="Punjab", district="Ludhiana", market="Khanna")
    evidence = await retriever.retrieve(
        db=db_session,
        query="What is the wheat price in Khanna mandi?",
        intent=AgriculturalIntent.MANDI_PRICE,
        context=ctx,
    )

    # Must be strictly empty so the advisor abstains
    assert len(evidence) == 0


# =============================================================================
# Test 4: Authoritative production_cached Fallback
# =============================================================================
@pytest.mark.asyncio
async def test_authoritative_production_cached_fallback(db_session):
    """
    Verifies that when live provider sync fails, valid records tagged
    production_cached are retrieved as authoritative evidence with explicit arrival_date.
    """
    cached_record = MandiPrice(
        id=str(uuid.uuid4()),
        state="Haryana",
        district="Karnal",
        market="Karnal",
        commodity="Wheat",
        variety="PBW-343",
        grade="FAQ",
        arrival_date=date(2026, 9, 22),
        min_price=2450.0,
        max_price=2600.0,
        modal_price=2550.0,
        source="Agmarknet / data.gov.in",
        data_origin="production_cached",
    )
    db_session.add(cached_record)
    db_session.commit()

    retriever = RetrievalService(embedding_provider=DeterministicMockEmbeddingProvider(dimension=768))

    ctx = FarmerContextDTO(crop="Wheat", state="Haryana", district="Karnal", market="Karnal")
    evidence = await retriever.retrieve(
        db=db_session,
        query="Wheat price in Karnal",
        intent=AgriculturalIntent.MANDI_PRICE,
        context=ctx,
    )

    assert len(evidence) == 1
    assert evidence[0].data_origin == "production_cached"
    assert evidence[0].status == "authoritative"
    assert evidence[0].metadata["arrival_date"] == "2026-09-22"
    assert evidence[0].metadata["modal_price"] == 2550.0
