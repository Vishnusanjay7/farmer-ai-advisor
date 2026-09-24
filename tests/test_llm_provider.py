import pytest
from unittest.mock import AsyncMock, patch
import httpx
from backend.app.providers.llm_provider import GeminiLLMProvider, MockLLMProvider, SUPPORTED_PRODUCTION_MODELS


# ------------------------------------------------------------------------------
# Test 1: Primary Model Success (gemini-3.8-flash)
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_gemini_primary_success():
    provider = GeminiLLMProvider(
        api_key="mock-api-key-test",
        model="gemini-3.8-flash",
        fallback_model="gemini-3.5-flash",
        max_retries=1,
    )

    mock_resp_json = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "Wheat should be irrigated at CRI stage (21 days after sowing)."}]
                }
            }
        ]
    }

    mock_response = httpx.Response(
        status_code=200,
        json=mock_resp_json,
        request=httpx.Request("POST", "https://mock.endpoint"),
    )

    with patch.object(provider, "_call_gemini_model", new=AsyncMock(return_value=mock_response)) as mock_call:
        res = await provider.generate_grounded_response(
            system_prompt="Test System Prompt",
            user_query="Wheat irrigation schedule",
            context_chunks=["Irrigate wheat at CRI stage (21 DAS)."],
            farmer_context={"language": "en-IN"},
        )

        assert res.is_grounded is True
        assert res.evidence_sufficient is True
        assert "CRI stage" in res.answer_text
        assert mock_call.call_count == 1
        # Called with primary model
        assert mock_call.call_args[0][1] == "gemini-3.8-flash"


# ------------------------------------------------------------------------------
# Test 2: Primary Transient 503 + Fallback Success (gemini-3.5-flash)
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_gemini_primary_503_fallback_success():
    provider = GeminiLLMProvider(
        api_key="mock-api-key-test",
        model="gemini-3.8-flash",
        fallback_model="gemini-3.5-flash",
        max_retries=1,
    )

    resp_503 = httpx.Response(
        status_code=503,
        text="The model is overloaded. Please try again later.",
        request=httpx.Request("POST", "https://mock.endpoint"),
    )

    mock_resp_json = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "Fallback model synthesized advice for yellow rust."}]
                }
            }
        ]
    }
    resp_200 = httpx.Response(
        status_code=200,
        json=mock_resp_json,
        request=httpx.Request("POST", "https://mock.endpoint"),
    )

    async def side_effect(client, model_name, payload, headers):
        if model_name == "gemini-3.8-flash":
            return resp_503
        elif model_name == "gemini-3.5-flash":
            return resp_200
        return resp_503

    with patch.object(provider, "_call_gemini_model", side_effect=side_effect) as mock_call:
        res = await provider.generate_grounded_response(
            system_prompt="Test System",
            user_query="Yellow rust control",
            context_chunks=["Spray propiconazole for yellow rust."],
            farmer_context={"language": "en-IN"},
        )

        assert res.is_grounded is True
        assert "Fallback model synthesized advice" in res.answer_text
        # Expected calls: 1 initial attempt + 1 retry on primary (both 503), then 1 fallback call = 3 total
        assert mock_call.call_count == 3


# ------------------------------------------------------------------------------
# Test 3: Primary + Fallback Failure (Both return 503)
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_gemini_primary_and_fallback_failure():
    provider = GeminiLLMProvider(
        api_key="mock-api-key-test",
        model="gemini-3.8-flash",
        fallback_model="gemini-3.5-flash",
        max_retries=1,
    )

    resp_503 = httpx.Response(
        status_code=503,
        text="Service Unavailable across cluster",
        request=httpx.Request("POST", "https://mock.endpoint"),
    )

    with patch.object(provider, "_call_gemini_model", new=AsyncMock(return_value=resp_503)):
        with pytest.raises(RuntimeError, match="Gemini provider unavailable: HTTP 503"):
            await provider.generate_grounded_response(
                system_prompt="Test System",
                user_query="Yellow rust control",
                context_chunks=["Spray propiconazole for yellow rust."],
                farmer_context={"language": "en-IN"},
            )


# ------------------------------------------------------------------------------
# Test 4: No Credentials (Missing API Key)
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_gemini_no_credentials():
    provider = GeminiLLMProvider(
        api_key=None,
        model="gemini-3.8-flash",
        fallback_model="gemini-3.5-flash",
    )
    provider.api_key = None

    with pytest.raises(ValueError, match="GeminiLLMProvider requires GEMINI_API_KEY"):
        await provider.generate_grounded_response(
            system_prompt="Test System",
            user_query="How to fertilize mustard?",
            context_chunks=["Mustard requires 80 kg N/ha."],
        )


# ------------------------------------------------------------------------------
# Test 5: Unsupported Model Configuration (Rejects Preview & Arbitrary Names)
# ------------------------------------------------------------------------------
def test_gemini_unsupported_model_configuration():
    # Unsupported primary model
    with pytest.raises(ValueError, match="not a supported production Gemini model"):
        GeminiLLMProvider(
            api_key="mock-key",
            model="gemini-3-flash-preview",  # Preview models strictly prohibited
        )

    # Unsupported fallback model
    with pytest.raises(ValueError, match="not a supported production Gemini model"):
        GeminiLLMProvider(
            api_key="mock-key",
            model="gemini-3.8-flash",
            fallback_model="arbitrary-preview-model-v1",
        )

    # Valid supported models must succeed
    p = GeminiLLMProvider(
        api_key="mock-key",
        model="gemini-3.8-flash",
        fallback_model="gemini-3.5-flash",
    )
    assert p.model == "gemini-3.8-flash"
    assert p.fallback_model == "gemini-3.5-flash"


# ------------------------------------------------------------------------------
# Existing Mock Provider Offline Isolation Tests
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mock_llm_provider_grounded_generation():
    provider = MockLLMProvider()
    res = await provider.generate_grounded_response(
        system_prompt="Test",
        user_query="What is the fertilizer schedule for wheat?",
        context_chunks=["Wheat requires 120 kg Nitrogen per hectare."],
        farmer_context={"language": "en-IN"},
    )
    assert res.is_grounded is True
    assert "120 kg Nitrogen per hectare" in res.answer_text


@pytest.mark.asyncio
async def test_mock_llm_provider_empty_chunks_abstention():
    provider = MockLLMProvider()
    res = await provider.generate_grounded_response(
        system_prompt="Test",
        user_query="Unknown question",
        context_chunks=[],
        farmer_context={"language": "en-IN"},
    )
    assert res.is_grounded is False
    assert res.evidence_sufficient is False
    assert "No authoritative evidence provided" in res.answer_text
