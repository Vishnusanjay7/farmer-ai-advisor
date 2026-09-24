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
