from backend.app.schemas.advisor import FarmerContextDTO
from backend.app.services.context_extractor import context_extractor


def test_context_extraction_full_entities():
    q = "I grow wheat in Punjab and need help with rust during Rabi season."
    ctx = context_extractor.extract(q)
    assert ctx.crop == "Wheat"
    assert ctx.state == "Punjab"
    assert ctx.season == "Rabi"
    assert ctx.pest_disease == "Rust"
    assert ctx.district is None  # Never hallucinated!


def test_context_extraction_zero_hallucination_empty():
    q = "What should I do about pests?"
    ctx = context_extractor.extract(q)
    assert ctx.crop is None
    assert ctx.state is None
    assert ctx.district is None
    assert ctx.season is None
    assert ctx.pest_disease is None


def test_context_extraction_regional_synonyms():
    q = "धान की फसल में पीला तना छेदक का प्रकोप है।"
    ctx = context_extractor.extract(q)
    assert ctx.crop == "Paddy"
    assert ctx.pest_disease == "Yellow stem borer"


def test_context_precedence_explicit_district_overrides_inherited_up():
    """Current query explicitly says Indore + inherited UP context -> resolves to Madhya Pradesh / Indore."""
    q = "What is the wheat price in Indore mandi?"
    init_ctx = FarmerContextDTO(state="Uttar Pradesh", crop="Wheat")
    ctx = context_extractor.extract(q, initial_context=init_ctx)
    assert ctx.district == "Indore"
    assert ctx.state == "Madhya Pradesh"
    assert ctx.crop == "Wheat"


def test_context_precedence_explicit_district_overrides_inherited_tamil_nadu():
    """Current query explicitly says Indore + inherited Tamil Nadu context -> resolves to Madhya Pradesh / Indore."""
    q = "What is the wheat price in Indore mandi?"
    init_ctx = FarmerContextDTO(state="Tamil Nadu", crop="Paddy")
    ctx = context_extractor.extract(q, initial_context=init_ctx)
    assert ctx.district == "Indore"
    assert ctx.state == "Madhya Pradesh"
    assert ctx.crop == "Wheat"  # Explicit query crop overrides inherited Paddy


def test_context_precedence_both_state_and_district_in_query():
    """Current query explicitly specifies both Madhya Pradesh + Indore -> uses current query."""
    q = "What is the wheat price in Indore, Madhya Pradesh?"
    init_ctx = FarmerContextDTO(state="Punjab", district="Ludhiana", crop="Paddy")
    ctx = context_extractor.extract(q, initial_context=init_ctx)
    assert ctx.state == "Madhya Pradesh"
    assert ctx.district == "Indore"
    assert ctx.crop == "Wheat"


def test_context_precedence_followup_no_location_inherits_context():
    """Follow-up query with no location -> inherited context still works."""
    q = "What is the price of wheat?"
    init_ctx = FarmerContextDTO(state="Punjab", district="Ludhiana", crop="Wheat")
    ctx = context_extractor.extract(q, initial_context=init_ctx)
    assert ctx.state == "Punjab"
    assert ctx.district == "Ludhiana"
    assert ctx.crop == "Wheat"


def test_context_precedence_ambiguous_location_does_not_guess():
    """Ambiguous/unrecognized location entity -> does not invent or guess state."""
    q = "What is the wheat price in UnknownTown mandi?"
    ctx = context_extractor.extract(q)
    assert ctx.state is None
    assert ctx.district is None
    assert ctx.crop == "Wheat"
