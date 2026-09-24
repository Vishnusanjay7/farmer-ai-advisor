from backend.app.schemas.advisor import AgriculturalIntent
from backend.app.services.intent_classifier import intent_classifier


def test_intent_classification_crop_advisory():
    q = "What is the recommended fertilizer dosage of urea for wheat in Punjab?"
    intent, conf = intent_classifier.classify(q)
    assert intent == AgriculturalIntent.CROP_ADVISORY
    assert conf >= 0.70


def test_intent_classification_pest_disease():
    q = "How do I control yellow stem borer in paddy crop?"
    intent, conf = intent_classifier.classify(q)
    assert intent == AgriculturalIntent.PEST_DISEASE
    assert conf >= 0.70


def test_intent_classification_mandi_price():
    q = "What is today's mandi price of wheat in Indore?"
    intent, conf = intent_classifier.classify(q)
    assert intent == AgriculturalIntent.MANDI_PRICE
    assert conf >= 0.90


def test_intent_classification_government_scheme():
    q = "Am I eligible for PM-KISAN yojana benefits?"
    intent, conf = intent_classifier.classify(q)
    assert intent == AgriculturalIntent.GOVERNMENT_SCHEME
    assert conf >= 0.90


def test_intent_classification_unsupported_out_of_scope():
    q = "Who won the cricket match between India and Australia yesterday?"
    intent, conf = intent_classifier.classify(q)
    assert intent == AgriculturalIntent.UNSUPPORTED
    assert conf >= 0.90


def test_intent_classification_ambiguous_safety():
    # Ambiguous query that contains no agricultural, scheme, or mandi keywords
    q = "Can you help me solve this problem quickly?"
    intent, conf = intent_classifier.classify(q)
    assert intent == AgriculturalIntent.UNSUPPORTED
    # Must NOT be forced into crop advisory or pest disease
    assert intent not in (AgriculturalIntent.CROP_ADVISORY, AgriculturalIntent.PEST_DISEASE)
