import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import io
import json
import uuid
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.providers.stt_provider import MockSTTProvider
from backend.app.providers.tts_provider import MockTTSProvider
from backend.app.api.deps import get_stt_provider, get_tts_provider

# Make mock wav
def make_mock_wav_bytes(num_samples: int = 16000) -> bytes:
    total_audio_bytes = num_samples * 2
    total_chunk_size = 36 + total_audio_bytes
    riff_header = b"RIFF" + total_chunk_size.to_bytes(4, "little") + b"WAVE"
    fmt_chunk = b"fmt " + (16).to_bytes(4, "little") + (1).to_bytes(2, "little") + (1).to_bytes(2, "little") + (16000).to_bytes(4, "little") + (32000).to_bytes(4, "little") + (2).to_bytes(2, "little") + (16).to_bytes(2, "little")
    data_chunk = b"data" + total_audio_bytes.to_bytes(4, "little") + (b"\x00" * total_audio_bytes)
    return riff_header + fmt_chunk + data_chunk

def run_judge_demo():
    client = TestClient(app)
    app.dependency_overrides[get_stt_provider] = lambda: MockSTTProvider()
    app.dependency_overrides[get_tts_provider] = lambda: MockTTSProvider()

    results = {}
    conv_id = str(uuid.uuid4())

    # TURN 1: Voice in Hindi -> "गेहूं में सिंचाई कब करनी चाहिए?"
    print("--- Running Turn 1 ---")
    stt_audio = make_mock_wav_bytes(16000)
    # Upload to STT
    stt_res = client.post(
        "/api/v1/voice/stt",
        files={"audio_file": ("wheat_irrigation.wav", io.BytesIO(stt_audio), "audio/wav")},
        data={"language": "hi-IN"},
    )
    turn1_query = "गेहूं में सिंचाई कब करनी चाहिए?"
    res1 = client.post(
        "/api/v1/advisor/query",
        json={
            "query": turn1_query,
            "language": "hi-IN",
            "input_channel": "voice",
            "conversation_id": conv_id,
        },
    )
    t1_data = res1.json()
    # Trigger TTS
    tts_res1 = client.post(
        "/api/v1/voice/tts",
        json={"text": t1_data["response_text"], "language": "hi-IN"},
    )
    results["turn_1"] = {
        "user_query": turn1_query,
        "input_channel": "voice",
        "language": "hi-IN",
        "stt_status": stt_res.status_code,
        "detected_intent": t1_data["intent"],
        "extracted_context": t1_data["extracted_context"],
        "inherited_context": t1_data["inherited_context"],
        "response_text": t1_data["response_text"],
        "citations": t1_data["citations"],
        "data_origin": t1_data["data_origin"],
        "abstained": t1_data["abstained"],
        "tts_status": tts_res1.status_code,
        "tts_audio_format": tts_res1.json().get("audio_format"),
    }

    # TURN 2: Follow-up question -> "इसमें पीला रतुआ कैसे रोकें?"
    print("--- Running Turn 2 ---")
    turn2_query = "इसमें पीला रतुआ कैसे रोकें?"
    res2 = client.post(
        "/api/v1/advisor/query",
        json={
            "query": turn2_query,
            "language": "hi-IN",
            "input_channel": "voice",
            "conversation_id": conv_id,
        },
    )
    t2_data = res2.json()
    results["turn_2"] = {
        "user_query": turn2_query,
        "input_channel": "voice",
        "language": "hi-IN",
        "conversation_id": conv_id,
        "detected_intent": t2_data["intent"],
        "extracted_context": t2_data["extracted_context"],
        "inherited_context": t2_data["inherited_context"],
        "response_text": t2_data["response_text"],
        "citations": t2_data["citations"],
        "data_origin": t2_data["data_origin"],
        "abstained": t2_data["abstained"],
    }

    # TURN 3: Mandi Price -> "इंदौर मंडी में गेहूं का भाव"
    print("--- Running Turn 3 ---")
    turn3_query = "इंदौर मंडी में गेहूं का भाव"
    res3 = client.post(
        "/api/v1/advisor/query",
        json={
            "query": turn3_query,
            "language": "hi-IN",
            "input_channel": "text",
            "conversation_id": conv_id,
        },
    )
    t3_data = res3.json()
    results["turn_3"] = {
        "user_query": turn3_query,
        "input_channel": "text",
        "language": "hi-IN",
        "detected_intent": t3_data["intent"],
        "extracted_context": t3_data["extracted_context"],
        "llm_called": t3_data["llm_called"],
        "response_text": t3_data["response_text"],
        "citations": t3_data["citations"],
        "data_origin": t3_data["data_origin"],
        "abstained": t3_data["abstained"],
    }

    # TURN 4: Unsupported Out-of-Scope Query -> "कल का क्रिकेट मैच किसने जीता?"
    print("--- Running Turn 4 ---")
    turn4_query = "कल का क्रिकेट मैच किसने जीता?"
    res4 = client.post(
        "/api/v1/advisor/query",
        json={
            "query": turn4_query,
            "language": "hi-IN",
            "input_channel": "text",
            "conversation_id": conv_id,
        },
    )
    t4_data = res4.json()
    results["turn_4"] = {
        "user_query": turn4_query,
        "input_channel": "text",
        "language": "hi-IN",
        "detected_intent": t4_data["intent"],
        "llm_called": t4_data["llm_called"],
        "response_text": t4_data["response_text"],
        "abstained": t4_data["abstained"],
        "abstention_reason": t4_data["abstention_reason"],
    }

    app.dependency_overrides.clear()

    out_file = os.path.join(os.path.dirname(__file__), "judge_demo_results.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Judge demo results written to: {out_file}")

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    run_judge_demo()
