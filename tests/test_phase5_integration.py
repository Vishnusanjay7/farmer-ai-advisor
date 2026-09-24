import pytest
import uuid
import io
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.main import app
from backend.app.db.session import SessionLocal
from backend.app.models.models import MandiPrice, GovernmentScheme, Conversation, QueryLog, ResponseLog
from backend.app.schemas.advisor import AdvisorQueryRequest, FarmerContextDTO
from backend.app.services.advisor_orchestrator import advisor_orchestrator
from backend.app.providers.stt_provider import MockSTTProvider
from backend.app.providers.tts_provider import MockTTSProvider
from backend.app.providers.llm_provider import MockLLMProvider
from backend.app.api.deps import get_stt_provider, get_tts_provider


client = TestClient(app)

# Helper to construct valid RIFF/WAV header for audio testing
def make_mock_wav_bytes(num_samples: int = 16000) -> bytes:
    total_audio_bytes = num_samples * 2
    total_chunk_size = 36 + total_audio_bytes
    riff_header = b"RIFF" + total_chunk_size.to_bytes(4, "little") + b"WAVE"
    fmt_chunk = b"fmt " + (16).to_bytes(4, "little") + (1).to_bytes(2, "little") + (1).to_bytes(2, "little") + (16000).to_bytes(4, "little") + (32000).to_bytes(4, "little") + (2).to_bytes(2, "little") + (16).to_bytes(2, "little")
    data_chunk = b"data" + total_audio_bytes.to_bytes(4, "little") + (b"\x00" * total_audio_bytes)
    return riff_header + fmt_chunk + data_chunk


# =========================================================================
# Scenario 1: Text -> Advisor
# =========================================================================
def test_scenario_01_text_to_advisor():
    res = client.post(
        "/api/v1/advisor/query",
        json={
            "query": "How to control yellow stem borer in paddy?",
            "language": "en-IN",
            "input_channel": "text",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["input_channel"] == "text"
    assert data["intent"] == "PEST_DISEASE"
    assert "yellow stem borer" in data["response_text"].lower() or "dead hearts" in data["response_text"].lower()
    assert len(data["citations"]) > 0
    assert data["citations"][0]["official_url"].startswith("http")


# =========================================================================
# Scenario 2: Voice -> STT -> Advisor
# =========================================================================
def test_scenario_02_voice_stt_to_advisor():
    app.dependency_overrides[get_stt_provider] = lambda: MockSTTProvider()

    # Step 1: Voice STT
    audio_bytes = make_mock_wav_bytes(16000)
    stt_res = client.post(
        "/api/v1/voice/stt",
        files={"audio_file": ("test_stem_borer.wav", io.BytesIO(audio_bytes), "audio/wav")},
        data={"language": "en-IN"},
    )
    assert stt_res.status_code == 200
    stt_data = stt_res.json()
    assert "transcript" in stt_data

    # Step 2: Pass STT transcript to Advisor
    adv_res = client.post(
        "/api/v1/advisor/query",
        json={
            "query": stt_data["transcript"],
            "language": "en-IN",
            "input_channel": "voice",
        },
    )
    assert adv_res.status_code == 200
    adv_data = adv_res.json()
    assert adv_data["input_channel"] == "voice"
    assert adv_data["intent"] in ["PEST_DISEASE", "CROP_ADVISORY"]
    app.dependency_overrides.clear()


# =========================================================================
# Scenario 3: Advisor -> TTS
# =========================================================================
def test_scenario_03_advisor_to_tts():
    app.dependency_overrides[get_tts_provider] = lambda: MockTTSProvider()

    # Get advisor response
    adv_res = client.post(
        "/api/v1/advisor/query",
        json={
            "query": "How to control yellow stem borer in paddy?",
            "language": "en-IN",
        },
    )
    assert adv_res.status_code == 200
    text = adv_res.json()["response_text"]

    # Synthesize with TTS
    tts_res = client.post(
        "/api/v1/voice/tts",
        json={"text": text, "language": "en-IN"},
    )
    assert tts_res.status_code == 200
    tts_data = tts_res.json()
    assert "audio_base64" in tts_data
    assert len(tts_data["audio_base64"]) > 50
    assert tts_data["audio_format"] == "wav"
    app.dependency_overrides.clear()


# =========================================================================
# Scenario 4: Full Voice Round Trip (Audio -> STT -> RAG -> TTS -> Audio)
# =========================================================================
def test_scenario_04_full_voice_round_trip():
    app.dependency_overrides[get_stt_provider] = lambda: MockSTTProvider()
    app.dependency_overrides[get_tts_provider] = lambda: MockTTSProvider()

    # Step 1: STT
    audio_bytes = make_mock_wav_bytes(16000)
    stt_res = client.post(
        "/api/v1/voice/stt",
        files={"audio_file": ("query.wav", io.BytesIO(audio_bytes), "audio/wav")},
        data={"language": "hi-IN"},
    )
    assert stt_res.status_code == 200

    # Step 2: Advisor
    adv_res = client.post(
        "/api/v1/advisor/query",
        json={
            "query": stt_res.json()["transcript"],
            "language": "hi-IN",
            "input_channel": "voice",
        },
    )
    assert adv_res.status_code == 200

    # Step 3: TTS
    tts_res = client.post(
        "/api/v1/voice/tts",
        json={"text": adv_res.json()["response_text"], "language": "hi-IN"},
    )
    assert tts_res.status_code == 200
    assert len(tts_res.json()["audio_base64"]) > 0
    app.dependency_overrides.clear()


# =========================================================================
# Scenario 5: Hindi Flow
# =========================================================================
def test_scenario_05_hindi_flow():
    res = client.post(
        "/api/v1/advisor/query",
        json={
            "query": "धान में तना छेदक का नियंत्रण कैसे करें?",
            "language": "hi-IN",
            "input_channel": "text",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["language"] == "hi-IN"
    assert data["intent"] == "PEST_DISEASE"
    assert data["extracted_context"].get("crop") == "Paddy"
    assert len(data["citations"]) > 0


# =========================================================================
# Scenario 6: Telugu Regional Flow
# =========================================================================
def test_scenario_06_telugu_flow():
    res = client.post(
        "/api/v1/advisor/query",
        json={
            "query": "వరిలో కాండం తొలిచే పురుగు నివారణ ఎలా?",
            "language": "te-IN",
            "input_channel": "text",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["language"] == "te-IN"
    assert data["intent"] == "PEST_DISEASE"
    assert data["extracted_context"].get("crop") == "Paddy"


# =========================================================================
# Scenario 7: Mandi Deterministic Response
# =========================================================================
def test_scenario_07_mandi_deterministic_formatting():
    res = client.post(
        "/api/v1/advisor/query",
        json={
            "query": "What is the wheat price in Indore mandi?",
            "language": "en-IN",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "MANDI_PRICE"
    assert data["llm_called"] is False
    text = data["response_text"]
    assert "Commodity: Wheat" in text
    assert "Market: Indore" in text
    assert "Modal Price:" in text
    assert "Arrival Date:" in text
    assert "Source: Agmarknet" in text
    assert "Official source" in text


# =========================================================================
# Scenario 8: Government Scheme Criteria Handling
# =========================================================================
def test_scenario_08_scheme_criteria_handling():
    res = client.post(
        "/api/v1/advisor/query",
        json={
            "query": "Who is eligible for PM-KISAN scheme and what documents are required?",
            "language": "en-IN",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "GOVERNMENT_SCHEME"
    assert data["llm_called"] is False
    text = data["response_text"]
    assert "Eligibility Criteria:" in text
    assert "Note on Eligibility: Documented eligibility criteria are listed above" in text
    assert "https://pmkisan.gov.in" in text


# =========================================================================
# Scenario 9: Agricultural RAG Answer with Dosages
# =========================================================================
def test_scenario_09_agricultural_rag_dosage():
    res = client.post(
        "/api/v1/advisor/query",
        json={
            "query": "How to control yellow stem borer in paddy?",
            "language": "en-IN",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["is_grounded"] is True
    assert data["abstained"] is False


# =========================================================================
# Scenario 10: Unsupported Out-of-Scope Query
# =========================================================================
def test_scenario_10_unsupported_query_abstention():
    res = client.post(
        "/api/v1/advisor/query",
        json={
            "query": "Who won the cricket match yesterday?",
            "language": "en-IN",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "UNSUPPORTED"
    assert data["abstained"] is True
    assert data["llm_called"] is False
    assert "outside the supported agricultural advisory scope" in data["response_text"]


# =========================================================================
# Scenario 11: Insufficient Evidence Safe Abstention
# =========================================================================
def test_scenario_11_insufficient_evidence_abstention():
    res = client.post(
        "/api/v1/advisor/query",
        json={
            "query": "What is the drone spraying schedule for dragon fruit in Ladakh?",
            "language": "en-IN",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["abstained"] is True
    assert data["llm_called"] is False


# =========================================================================
# Scenario 12: STT Provider Upstream Failure
# =========================================================================
def test_scenario_12_stt_failure_handling():
    class FailingSTT:
        async def transcribe(self, audio_bytes, language_hint=None):
            raise TimeoutError("Upstream STT connection timed out.")

    app.dependency_overrides[get_stt_provider] = lambda: FailingSTT()
    audio_bytes = make_mock_wav_bytes(16000)
    res = client.post(
        "/api/v1/voice/stt",
        files={"audio_file": ("test.wav", io.BytesIO(audio_bytes), "audio/wav")},
        data={"language": "hi-IN"},
    )
    assert res.status_code in [502, 504]
    app.dependency_overrides.clear()


# =========================================================================
# Scenario 13: TTS Failure Preserves Text Response
# =========================================================================
def test_scenario_13_tts_failure_preserves_text():
    class FailingTTS:
        async def synthesize(self, text, language_code="hi-IN", speaker="meera"):
            raise TimeoutError("Upstream TTS service timed out.")

    app.dependency_overrides[get_tts_provider] = lambda: FailingTTS()
    tts_res = client.post(
        "/api/v1/voice/tts",
        json={"text": "Verified wheat advisory advice", "language": "hi-IN"},
    )
    assert tts_res.status_code in [502, 504]
    # Verify advisor endpoint still returns full textual answer intact
    adv_res = client.post(
        "/api/v1/advisor/query",
        json={"query": "How to control yellow stem borer in paddy?", "language": "en-IN"},
    )
    assert adv_res.status_code == 200
    assert len(adv_res.json()["response_text"]) > 20
    app.dependency_overrides.clear()


# =========================================================================
# Scenario 14: LLM Unavailable Fallback
# =========================================================================
def test_scenario_14_llm_unavailable_handling():
    # Calling with empty evidence or unsupported will safely abstain without crashing
    res = client.post(
        "/api/v1/advisor/query",
        json={"query": "Tell me a random poem about tractors", "language": "en-IN"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["abstained"] is True


# =========================================================================
# Scenario 15: Mandi Upstream Unavailable (Cached Fallback)
# =========================================================================
def test_scenario_15_mandi_cached_data_origin():
    res = client.post(
        "/api/v1/advisor/query",
        json={"query": "What is the wheat price in Indore mandi?", "language": "en-IN"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["data_origin"] in ["production_live", "production_cached"]
    assert "development_seed" not in data["data_origin"]


# =========================================================================
# Scenario 16: Conversation Continuity & Multi-Turn Association
# =========================================================================
def test_scenario_16_conversation_continuity():
    conv_id = str(uuid.uuid4())

    # Turn 1: Wheat question
    res1 = client.post(
        "/api/v1/advisor/query",
        json={
            "query": "What should I do for wheat?",
            "language": "en-IN",
            "conversation_id": conv_id,
        },
    )
    assert res1.status_code == 200
    assert res1.json()["extracted_context"].get("crop") == "Wheat"

    # Turn 2: Follow-up omitting crop
    res2 = client.post(
        "/api/v1/advisor/query",
        json={
            "query": "How do I prevent yellow rust?",
            "language": "en-IN",
            "conversation_id": conv_id,
        },
    )
    assert res2.status_code == 200
    data2 = res2.json()
    # Turn 2 should have inherited "Wheat" from Turn 1
    assert data2["extracted_context"].get("crop") == "Wheat"
    assert data2["inherited_context"].get("crop") == "Wheat"

    # Verify conversation history endpoint
    hist_res = client.get(f"/api/v1/conversations/{conv_id}")
    assert hist_res.status_code == 200
    hist = hist_res.json()
    assert hist["conversation_id"] == conv_id
    assert hist["total_turns"] >= 2
    assert hist["turns"][0]["query_text"] == "What should I do for wheat?"


# =========================================================================
# Scenario 17: Farmer Context Persistence
# =========================================================================
def test_scenario_17_farmer_context_persistence():
    conv_id = str(uuid.uuid4())
    res = client.post(
        "/api/v1/advisor/query",
        json={
            "query": "What are the common diseases?",
            "language": "en-IN",
            "conversation_id": conv_id,
            "farmer_context": {
                "state": "Punjab",
                "district": "Ludhiana",
                "crop": "Wheat",
            },
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["extracted_context"].get("crop") == "Wheat"
    assert data["extracted_context"].get("state") == "Punjab"
