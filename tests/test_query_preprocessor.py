import pytest
from backend.app.services.query_preprocessor import query_preprocessor


def test_query_preprocessing_normalization_and_preservation():
    raw_query = "  धान में   पीला तना छेदक \u200B कीट का नियंत्रण कैसे करें?   "
    res = query_preprocessor.process(query=raw_query, language="hi-IN")

    assert res.original_query == raw_query.strip()
    assert "\u200B" not in res.normalized_query
    assert "  " not in res.normalized_query
    assert res.normalized_query == "धान में पीला तना छेदक कीट का नियंत्रण कैसे करें?"
    assert res.language == "hi-IN"
    assert res.request_id is not None
    assert res.timestamp is not None


def test_empty_query_rejection():
    with pytest.raises(ValueError, match="Query string cannot be empty"):
        query_preprocessor.process(query="   ", language="en-IN")
