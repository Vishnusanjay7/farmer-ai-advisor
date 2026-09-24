import inspect
import pytest
from backend.app.providers.base import (
    SpeechToTextProvider,
    TextToSpeechProvider,
    MandiPriceProvider,
    GovernmentSchemeProvider,
    LLMProvider,
    EmbeddingProvider,
    STTResult,
    TTSResult,
    MandiPriceDTO,
    GovernmentSchemeDTO,
    GroundedSourceCitation,
    LLMGroundedResponse,
)


def test_provider_interfaces_are_abstract():
    """Verify that provider interfaces cannot be instantiated directly."""
    for provider_cls in [
        SpeechToTextProvider,
        TextToSpeechProvider,
        MandiPriceProvider,
        GovernmentSchemeProvider,
        LLMProvider,
        EmbeddingProvider,
    ]:
        with pytest.raises(TypeError):
            provider_cls()


def test_grounded_response_dto():
    """Verify that grounded response DTO tracks citations and disclaimers."""
    citation = GroundedSourceCitation(
        document_id="doc-123",
        title="Package of Practices for Rice",
        issuing_authority="ICAR-IIRR",
        publication_year=2024,
        similarity_score=0.92,
    )
    response = LLMGroundedResponse(
        answer_text="Sample grounded answer.",
        language_code="te-IN",
        intent="PEST_DISEASE",
        citations=[citation],
        is_grounded=True,
        disclaimer_applied=False,
        evidence_sufficient=True,
    )
    assert response.is_grounded is True
    assert len(response.citations) == 1
    assert response.citations[0].issuing_authority == "ICAR-IIRR"


def test_mandi_price_dto_data_origin():
    """Verify MandiPriceDTO supports data origin distinction."""
    dto = MandiPriceDTO(
        state="Maharashtra",
        district="Nashik",
        market="Lasalgaon",
        commodity="Onion",
        arrival_date="2026-09-22",
        min_price=1800.0,
        max_price=2400.0,
        modal_price=2200.0,
        source="Agmarknet",
        data_origin="production_live",
        fetched_at="2026-09-22T19:00:00Z",
    )
    assert dto.data_origin == "production_live"
    assert dto.commodity == "Onion"
