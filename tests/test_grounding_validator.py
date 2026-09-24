from backend.app.schemas.advisor import AgriculturalIntent, EvidenceItemDTO
from backend.app.services.grounding_validator import grounding_validator


def test_pre_llm_validation_unsupported_intent():
    is_valid, reason = grounding_validator.validate_pre_llm(
        intent=AgriculturalIntent.UNSUPPORTED,
        evidence=[],
    )
    assert not is_valid
    assert "outside the supported agricultural advisory scope" in reason


def test_pre_llm_validation_empty_evidence():
    is_valid, reason = grounding_validator.validate_pre_llm(
        intent=AgriculturalIntent.CROP_ADVISORY,
        evidence=[],
    )
    assert not is_valid
    assert "No verified official agricultural records" in reason


def test_pre_llm_validation_low_relevance_threshold():
    low_evidence = [
        EvidenceItemDTO(
            evidence_id="ev1",
            source_name="Test",
            title="Test Title",
            issuing_authority="ICAR",
            content="Some loosely related content",
            relevance_score=0.30,  # Below 0.55 threshold
            status="insufficient",
        )
    ]
    is_valid, reason = grounding_validator.validate_pre_llm(
        intent=AgriculturalIntent.CROP_ADVISORY,
        evidence=low_evidence,
        similarity_threshold=0.55,
    )
    assert not is_valid
    assert "below the safety threshold" in reason


def test_post_llm_validation_unsupported_chemical_dosage():
    evidence = [
        EvidenceItemDTO(
            evidence_id="ev1",
            source_name="ICAR-IIRR",
            title="Rice POP",
            issuing_authority="ICAR",
            content="Apply chlorantraniliprole 0.4% G at 10 kg/ha in nursery.",
            relevance_score=0.90,
            status="authoritative",
        )
    ]
    # LLM hallucinates 250 ml/ha of monocrotophos (250 is nowhere in evidence!)
    generated = "You should apply monocrotophos at 250 ml per hectare."
    is_valid, reason = grounding_validator.validate_post_llm(
        generated_text=generated,
        evidence=evidence,
        intent=AgriculturalIntent.PEST_DISEASE,
    )
    assert not is_valid
    assert "unverified chemical dosage" in reason


def test_post_llm_validation_supported_text():
    evidence = [
        EvidenceItemDTO(
            evidence_id="ev1",
            source_name="ICAR-IIRR",
            title="Rice POP",
            issuing_authority="ICAR",
            content="Apply chlorantraniliprole at 10 kg per hectare.",
            relevance_score=0.90,
            status="authoritative",
        )
    ]
    generated = "According to ICAR, apply chlorantraniliprole at 10 kg per hectare."
    is_valid, reason = grounding_validator.validate_post_llm(
        generated_text=generated,
        evidence=evidence,
        intent=AgriculturalIntent.PEST_DISEASE,
    )
    assert is_valid
    assert reason is None
