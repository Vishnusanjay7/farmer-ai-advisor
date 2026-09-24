import pytest
from unittest.mock import patch, MagicMock
from backend.app.core.config import settings
from backend.app.providers.embedding_provider import (
    DeterministicMockEmbeddingProvider,
    GeminiEmbeddingProvider,
    get_embedding_provider,
)
from backend.app.services.retrieval_service import RetrievalService


@pytest.mark.asyncio
async def test_deterministic_mock_embedding_dimension():
    provider = DeterministicMockEmbeddingProvider(dimension=768)
    vector = await provider.generate_embedding("Paddy stem borer management")

    assert len(vector) == 768
    # Verify deterministic reproducibility
    vector_repeat = await provider.generate_embedding("Paddy stem borer management")
    assert vector == vector_repeat


@pytest.mark.asyncio
async def test_embedding_dimension_mismatch_detection():
    """Verify that dimension mismatches raise a ValueError rather than padding/truncating."""
    provider = GeminiEmbeddingProvider(api_key="mock_key")
    provider.expected_dimension = 768

    # Mock response returning incorrect dimension (e.g. 1536 from OpenAI)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"embedding": {"values": [0.1] * 1536}}

    with patch("httpx.AsyncClient.post", return_value=mock_response):
        with pytest.raises(ValueError, match="Embedding dimension mismatch"):
            await provider.generate_embedding("Sample text")


@pytest.mark.asyncio
async def test_gemini_correct_dimension_handling():
    provider = GeminiEmbeddingProvider(api_key="mock_key")
    provider.expected_dimension = 768

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"embedding": {"values": [0.05] * 768}}

    with patch("httpx.AsyncClient.post", return_value=mock_response) as mock_post:
        res = await provider.generate_embedding("Sample text")
        assert len(res) == 768
        # Verify outputDimensionality was sent in the payload
        sent_payload = mock_post.call_args[1]["json"]
        assert sent_payload["outputDimensionality"] == 768
        assert sent_payload["model"] == f"models/{settings.EMBEDDING_MODEL}"


def test_development_without_gemini_key_uses_deterministic_mock(monkeypatch):
    """In development, missing Gemini key falls back to DeterministicMockEmbeddingProvider."""
    monkeypatch.setattr("backend.app.core.config.settings.ENVIRONMENT", "development")
    monkeypatch.setattr("backend.app.core.config.settings.GEMINI_API_KEY", None)
    monkeypatch.setattr("backend.app.core.config.settings.LLM_API_KEY", None)

    provider = get_embedding_provider()
    assert isinstance(provider, DeterministicMockEmbeddingProvider)
    assert provider.dimension == 768


def test_staging_without_gemini_key_raises_error(monkeypatch):
    """In staging, missing Gemini key fails fast without silent mock fallback."""
    monkeypatch.setattr("backend.app.core.config.settings.ENVIRONMENT", "staging")
    monkeypatch.setattr("backend.app.core.config.settings.GEMINI_API_KEY", None)
    monkeypatch.setattr("backend.app.core.config.settings.LLM_API_KEY", None)

    with pytest.raises(ValueError, match="GEMINI_API_KEY is required in staging mode for vector embeddings"):
        get_embedding_provider()


def test_production_without_gemini_key_raises_error(monkeypatch):
    """In production, missing Gemini key fails fast without silent mock fallback."""
    monkeypatch.setattr("backend.app.core.config.settings.ENVIRONMENT", "production")
    monkeypatch.setattr("backend.app.core.config.settings.GEMINI_API_KEY", None)
    monkeypatch.setattr("backend.app.core.config.settings.LLM_API_KEY", None)

    with pytest.raises(ValueError, match="GEMINI_API_KEY is required in production mode for vector embeddings"):
        get_embedding_provider()


def test_staging_with_gemini_configuration_selects_gemini_provider(monkeypatch):
    """In staging, configured Gemini key selects GeminiEmbeddingProvider."""
    monkeypatch.setattr("backend.app.core.config.settings.ENVIRONMENT", "staging")
    monkeypatch.setattr("backend.app.core.config.settings.GEMINI_API_KEY", "test_gemini_key")
    monkeypatch.setattr("backend.app.core.config.settings.EMBEDDING_MODEL", "gemini-embedding-001")

    provider = get_embedding_provider()
    assert isinstance(provider, GeminiEmbeddingProvider)
    assert provider.model == "gemini-embedding-001"
    assert provider.expected_dimension == 768


def test_configured_embedding_model_passed_into_gemini_provider(monkeypatch):
    """Settings.EMBEDDING_MODEL is propagated directly into GeminiEmbeddingProvider."""
    monkeypatch.setattr("backend.app.core.config.settings.EMBEDDING_MODEL", "gemini-embedding-001")
    provider = GeminiEmbeddingProvider(api_key="mock_key")
    assert provider.model == "gemini-embedding-001"
    assert provider.expected_dimension == 768


def test_embedding_dimension_remains_exactly_768():
    """Embedding dimension setting must remain exactly 768."""
    assert settings.EMBEDDING_DIMENSION == 768


def test_retrieval_service_cannot_bypass_staging_production_guard(monkeypatch):
    """RetrievalService routes through get_embedding_provider and cannot silently fall back to mock in staging."""
    monkeypatch.setattr("backend.app.core.config.settings.ENVIRONMENT", "staging")
    monkeypatch.setattr("backend.app.core.config.settings.GEMINI_API_KEY", None)
    monkeypatch.setattr("backend.app.core.config.settings.LLM_API_KEY", None)

    with pytest.raises(ValueError, match="GEMINI_API_KEY is required in staging mode"):
        RetrievalService()

    # In production without key -> must also raise
    monkeypatch.setattr("backend.app.core.config.settings.ENVIRONMENT", "production")
    with pytest.raises(ValueError, match="GEMINI_API_KEY is required in production mode"):
        RetrievalService()

    # In staging WITH key -> selects GeminiEmbeddingProvider with configured model
    monkeypatch.setattr("backend.app.core.config.settings.GEMINI_API_KEY", "test_gemini_key")
    monkeypatch.setattr("backend.app.core.config.settings.EMBEDDING_MODEL", "gemini-embedding-001")
    retriever = RetrievalService()
    assert isinstance(retriever.embedding_provider, GeminiEmbeddingProvider)
    assert retriever.embedding_provider.model == "gemini-embedding-001"

