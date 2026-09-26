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


# ---------------------------------------------------------------------------
# CROP PRECEDENCE REGRESSION TESTS
# Root cause: tomato (and other high-volume mandi crops) were absent from the
# CROPS dictionary. When the query said "tomato" but the crop was not
# recognized, extracted["crop"] was never set, so the fallback
# `extracted.get("crop") or init_dict.get("crop")` silently returned the
# stale inherited crop (e.g., Wheat).
# ---------------------------------------------------------------------------


def test_crop_precedence_test1_tomato_overrides_inherited_wheat():
    """TEST 1: Explicit tomato in query overrides inherited crop=Wheat."""
    from backend.app.schemas.advisor import FarmerContextDTO
    init_ctx = FarmerContextDTO(crop="Wheat", state="Tamil Nadu")
    ctx = context_extractor.extract(
        "What is the rate of tomato in Tiruppur?", initial_context=init_ctx
    )
    assert ctx.crop == "Tomato"
    assert ctx.district == "Tiruppur"
    assert ctx.state == "Tamil Nadu"


def test_crop_precedence_test2_wheat_overrides_inherited_rice():
    """TEST 2: Explicit wheat in query overrides inherited crop=Rice."""
    from backend.app.schemas.advisor import FarmerContextDTO
    init_ctx = FarmerContextDTO(crop="Rice")
    ctx = context_extractor.extract(
        "What is the wheat price in Tiruppur?", initial_context=init_ctx
    )
    assert ctx.crop == "Wheat"


def test_crop_precedence_test3_tomato_overrides_wheat_with_indore():
    """TEST 3: Explicit tomato + Indore query overrides Wheat + prior context."""
    from backend.app.schemas.advisor import FarmerContextDTO
    init_ctx = FarmerContextDTO(crop="Wheat")
    ctx = context_extractor.extract(
        "What is the tomato price in Indore?", initial_context=init_ctx
    )
    assert ctx.crop == "Tomato"
    assert ctx.district == "Indore"
    assert ctx.state == "Madhya Pradesh"


def test_crop_precedence_test4_tomato_overrides_wheat_and_punjab():
    """TEST 4: Both crop AND location from current query override full inherited context."""
    from backend.app.schemas.advisor import FarmerContextDTO
    init_ctx = FarmerContextDTO(crop="Wheat", state="Punjab", district="Ludhiana")
    ctx = context_extractor.extract(
        "What is tomato price in Tiruppur?", initial_context=init_ctx
    )
    assert ctx.crop == "Tomato"
    assert ctx.district == "Tiruppur"
    assert ctx.state == "Tamil Nadu"


def test_crop_precedence_test5_followup_inherits_crop_and_location():
    """TEST 5: Genuine follow-up inherits crop+location from prior turn."""
    from backend.app.schemas.advisor import FarmerContextDTO
    init_ctx = FarmerContextDTO(crop="Wheat", state="Tamil Nadu", district="Tiruppur")
    ctx = context_extractor.extract("What about today?", initial_context=init_ctx)
    assert ctx.crop == "Wheat"
    assert ctx.district == "Tiruppur"
    assert ctx.state == "Tamil Nadu"


def test_crop_precedence_test6_tomato_replaces_wheat_inherits_location():
    """TEST 6: Explicit new crop overrides inherited; location inherits when no conflict."""
    from backend.app.schemas.advisor import FarmerContextDTO
    init_ctx = FarmerContextDTO(crop="Wheat", state="Tamil Nadu", district="Tiruppur")
    ctx = context_extractor.extract(
        "What is the tomato price?", initial_context=init_ctx
    )
    assert ctx.crop == "Tomato"
    assert ctx.state == "Tamil Nadu"
    assert ctx.district == "Tiruppur"


def test_crop_precedence_test7_no_crop_no_hallucination():
    """TEST 7: No crop in query and no initial context -> crop is None."""
    ctx = context_extractor.extract("What is the price in Tiruppur?")
    assert ctx.crop is None
    assert ctx.district == "Tiruppur"
    assert ctx.state == "Tamil Nadu"


def test_crop_precedence_matrix_rice_followup_inherits():
    """Matrix: previous crop=Rice, follow-up -> Rice inherited."""
    from backend.app.schemas.advisor import FarmerContextDTO
    init_ctx = FarmerContextDTO(crop="Rice", state="Punjab", district="Ludhiana")
    ctx = context_extractor.extract("What about today?", initial_context=init_ctx)
    assert ctx.crop == "Rice"


def test_crop_precedence_new_crops_recognized():
    """All newly added mandi crops must be recognized from their English names."""
    cases = {
        "What is the onion price?": "Onion",
        "What is the potato rate?": "Potato",
        "What is the groundnut price?": "Groundnut",
        "What is the turmeric rate?": "Turmeric",
        "What is the bajra price?": "Bajra",
        "What is the jowar rate?": "Jowar",
        "What is the banana price?": "Banana",
        "What is the mango price?": "Mango",
        "What is the garlic rate?": "Garlic",
        "What is the ginger price?": "Ginger",
        "What is the arhar price?": "Arhar",
        "What is the sunflower price?": "Sunflower",
    }
    for query, expected_crop in cases.items():
        ctx = context_extractor.extract(query)
        assert ctx.crop == expected_crop, (
            "Query " + repr(query) + ": expected " + repr(expected_crop) + ", got " + repr(ctx.crop)
        )


def test_pulse_taxonomy_distinct_canonical_crops():
    """Verify distinct canonical pulse crops and aliases (arhar, moong, urad, masoor)."""
    pulse_expectations = {
        "What is the arhar price?": "Arhar",
        "What is the toor price?": "Arhar",
        "What is the tur price?": "Arhar",
        "What is the pigeon pea price?": "Arhar",
        "What is the moong price?": "Moong",
        "What is the mung price?": "Moong",
        "What is the green gram price?": "Moong",
        "What is the urad price?": "Urad",
        "What is the black gram price?": "Urad",
        "What is the masoor price?": "Masoor",
        "What is the lentil price?": "Masoor",
        "What is the red lentil price?": "Masoor",
    }
    for query, expected_crop in pulse_expectations.items():
        ctx = context_extractor.extract(query)
        assert ctx.crop == expected_crop, (
            f"Query '{query}': expected '{expected_crop}', got '{ctx.crop}'"
        )


def test_dal_daal_not_extracted_as_crop():
    """Verify dal/daal is never extracted as a crop alias (too ambiguous for mandi commodities)."""
    dal_queries = [
        "What is the dal price?",
        "dal roti recipe",
        "What is the daal rate today?",
        "daal chawal recipe",
        "how to cook yellow dal",
    ]
    disallowed_crops = {"Lentil", "Arhar", "Moong", "Urad", "Masoor"}
    for query in dal_queries:
        ctx = context_extractor.extract(query)
        assert ctx.crop not in disallowed_crops, (
            f"Query '{query}' incorrectly extracted '{ctx.crop}' from ambiguous dal/daal term"
        )
        assert ctx.crop is None, f"Query '{query}' expected crop=None, got '{ctx.crop}'"


def test_crop_precedence_pulses_override_inherited_wheat():
    """Inherited Wheat must NOT override an explicitly mentioned Arhar/Moong/Urad/Masoor."""
    from backend.app.schemas.advisor import FarmerContextDTO

    init_ctx = FarmerContextDTO(crop="Wheat", state="Madhya Pradesh", district="Indore")
    queries_and_expected = [
        ("What is the arhar price?", "Arhar"),
        ("What is the toor price?", "Arhar"),
        ("What is the tur price?", "Arhar"),
        ("What is the moong price?", "Moong"),
        ("What is the mung price?", "Moong"),
        ("What is the urad price?", "Urad"),
        ("What is the masoor price?", "Masoor"),
        ("What is the lentil price?", "Masoor"),
    ]
    for query, expected_crop in queries_and_expected:
        ctx = context_extractor.extract(query, initial_context=init_ctx)
        assert ctx.crop == expected_crop, (
            f"Explicit '{expected_crop}' in '{query}' was overridden by inherited Wheat: got '{ctx.crop}'"
        )
        # Location context should safely inherit when not conflicted
        assert ctx.state == "Madhya Pradesh"
        assert ctx.district == "Indore"


def test_pulse_multilingual_aliases():
    """Verify regional language aliases for distinct pulse commodities."""
    cases = {
        # Arhar: Hindi, Marathi, Telugu, Tamil
        "अरहर का भाव क्या है?": "Arhar",
        "तूर का भाव बताओ": "Arhar",
        "కందులు ధర ఎంత": "Arhar",
        "துவரை விலை என்ன": "Arhar",
        # Moong: Hindi, Telugu, Tamil
        "मूंग का भाव क्या है?": "Moong",
        "పెసలు ధర ఎంత": "Moong",
        "பாசிப்பயறு விலை என்ன": "Moong",
        # Urad: Hindi, Telugu, Tamil
        "उड़द का रेट क्या है?": "Urad",
        "మినుములు ధర ఎంత": "Urad",
        "உளுந்து விலை என்ன": "Urad",
        # Masoor: Hindi, Telugu
        "मसूर का भाव क्या है?": "Masoor",
        "మసూర్ ధర ఎంత": "Masoor",
    }
    for query, expected_crop in cases.items():
        ctx = context_extractor.extract(query)
        assert ctx.crop == expected_crop, (
            f"Multilingual query '{query}': expected '{expected_crop}', got '{ctx.crop}'"
        )


def test_pulse_followup_inherits_context():
    """Verify genuine follow-up queries retain inherited pulse crop context."""
    from backend.app.schemas.advisor import FarmerContextDTO

    pulses = ["Arhar", "Moong", "Urad", "Masoor"]
    for pulse in pulses:
        init_ctx = FarmerContextDTO(crop=pulse, state="Maharashtra", district="Nagpur")
        ctx = context_extractor.extract("What about tomorrow?", initial_context=init_ctx)
        assert ctx.crop == pulse
        assert ctx.state == "Maharashtra"
        assert ctx.district == "Nagpur"
