# Phase 5 Test Plan: End-to-End Verification Strategy

## 1. Objectives & Scope

This document details the complete end-to-end test strategy for Phase 5 of the Regional Language Voice-Based AI Advisory Assistant.
The testing framework ensures:
- Robust convergence of voice and text query paths onto the unified Conversational Advisor API.
- Zero factual hallucination and reliable pre-LLM abstention.
- Strict deterministic formatting of mandi prices and government schemes.
- Graceful degradation when external providers (Sarvam STT/TTS, Gemini LLM, Agmarknet) experience network or credential failures.
- Multi-lingual accuracy across Hindi, Telugu, Tamil, and English.
- Complete isolation of test executions without fabricated live claims.

---

## 2. Test Architecture & Environment

| Layer | Framework & Tools | Mode of Execution |
| :--- | :--- | :--- |
| **Backend Integration Suite** | `pytest`, `pytest-asyncio`, `FastAPI TestClient` | Deterministic Mock Providers (`MockLLMProvider`, `MockSpeechToTextProvider`, `MockTextToSpeechProvider`). |
| **Database Isolation** | SQLite in-memory / local `test_db.sqlite` | Automatic rollback per test session, pre-seeded with Phase 2 agricultural knowledge and schemes. |
| **Frontend Production Verification** | Next.js 16.3.5 Turbopack (`npm run build`) | Static analysis, TypeScript typechecking, zero build warnings. |
| **End-to-End Integration** | `tests/test_phase5_integration.py` | 17 focused test cases simulating full farmer interaction cycles. |

---

## 3. The 17 Core Integration Test Scenarios

### Test 1: Text → Advisor Pipeline
- **Input:** Text query `"What are the symptoms of Yellow Rust in wheat?"` in `en-IN`.
- **Pipeline:** Preprocessing → Intent (`PEST_DISEASE`) → Context (`Wheat`, `Yellow Rust`) → Vector Retrieval → LLM → Validation.
- **Assertions:**
  - Status code `200 OK`.
  - `llm_called` is `True`.
  - `response_text` contains verified symptoms (*linear yellow stripes on leaf blades*).
  - Citations include ICAR-IARI Wheat guide.

### Test 2: Voice → STT → Advisor Pipeline
- **Input:** Valid WebM audio binary of farmer asking about paddy stem borer in Hindi.
- **Pipeline:** `/api/v1/voice/stt` → transcript generation → `/api/v1/advisor/query`.
- **Assertions:**
  - STT returns transcript with high confidence.
  - Advisor detects `PEST_DISEASE` intent with `Paddy` context.
  - Answer contains ICAR-IIRR recommended IPM practices.

### Test 3: Advisor → TTS Pipeline
- **Input:** Grounded response text from advisor passed to `/api/v1/voice/tts` with `language="hi-IN"`.
- **Pipeline:** TTS Provider (Bulbul model) synthesizes audio.
- **Assertions:**
  - Status code `200 OK`.
  - Returns non-empty `audio_base64` string in valid WAV container format.
  - Audio duration $> 0.0$ seconds.

### Test 4: Full Voice Round Trip
- **Input:** Audio recording in $\rightarrow$ STT $\rightarrow$ Advisor Query $\rightarrow$ TTS $\rightarrow$ Audio out.
- **Pipeline:** Complete voice-in, voice-out loop.
- **Assertions:**
  - Query log is persisted in database with `input_channel="voice"`.
  - Response text matches synthesized voice audio text.
  - Latency breakdown is logged.

### Test 5: Hindi Language Flow
- **Input:** `"धान में तना छेदक की रोकथाम कैसे करें?"` (`hi-IN`).
- **Pipeline:** Query processed with Devanagari script preservation and Hindi stopwords filtering.
- **Assertions:**
  - Correct entity extraction: `crop="Paddy"`, `pest_disease="Yellow stem borer"`.
  - Retrieved citations show high relevance.
  - Final response delivers grounded management schedule in Hindi.

### Test 6: Telugu Regional Language Flow
- **Input:** `"వరిలో కాండం తొలిచే పురుగు నివారణ ఎలా?"` (`te-IN`).
- **Pipeline:** Unicode Telugu script normalization, Telugu synonym mapping in context extractor.
- **Assertions:**
  - Correct entity extraction: `crop="Paddy"`, `pest_disease="Yellow stem borer"`.
  - Response text generated in Telugu with verified cultural and biological recommendations.

### Test 7: Mandi Price Flow (Deterministic & Safe)
- **Input:** `"What is the wheat price in Indore mandi?"`.
- **Pipeline:** Intent `MANDI_PRICE` $\rightarrow$ Agmarknet structured retrieval $\rightarrow$ Deterministic formatting.
- **Assertions:**
  - `llm_called` is `False`.
  - Response contains `commodity`, `market`, `variety/grade`, `min_price`, `max_price`, `modal_price`, `arrival_date`, and `data_origin`.
  - Displays provenance badge: `"Official source • Live data"` or `"Official source • Cached data"`.

### Test 8: Government Scheme Flow
- **Input:** `"Who is eligible for PM-KISAN scheme and what documents are required?"`.
- **Pipeline:** Intent `GOVERNMENT_SCHEME` $\rightarrow$ `government_schemes` table retrieval $\rightarrow$ Deterministic formatting.
- **Assertions:**
  - `llm_called` is `False`.
  - Clearly distinguishes documented scheme eligibility criteria from individual farmer determination.
  - Contains raw portal URL (`https://pmkisan.gov.in`).

### Test 9: Agricultural RAG Grounded Query
- **Input:** Question on Cotton Pink Bollworm management.
- **Pipeline:** RAG hybrid vector + keyword retrieval against ICAR-CICR guide.
- **Assertions:**
  - Verified chemical dosage (e.g. *Spinetoram 11.7% SC @ 160 ml*) passes grounding validator.
  - Post-LLM validator ensures zero unapproved chemicals are injected.

### Test 10: Unsupported Out-of-Scope Query (Safe Abstention)
- **Input:** `"Who won the cricket match yesterday?"` or `"Tell me about bollywood movies"`.
- **Pipeline:** Intent classified as `UNSUPPORTED`.
- **Assertions:**
  - Immediate abstention before retrieval and LLM (`llm_called=False`, `abstained=True`).
  - Abstention reason: `"Query is outside the supported agricultural advisory scope."`.
  - Zero hallucination.

### Test 11: Insufficient Agricultural Evidence (Safe Abstention)
- **Input:** `"What is the drone spraying schedule for dragon fruit in Ladakh?"`.
- **Pipeline:** Retrieval against official knowledge base yields score $< 0.55$.
- **Assertions:**
  - Pre-LLM gate abstains (`llm_called=False`, `abstained=True`).
  - System refuses to fabricate unverified dragon fruit schedules in Ladakh.

### Test 12: STT Provider Upstream Failure Fallback
- **Input:** Uploaded audio fails in STT due to mock network drop / timeout.
- **Assertions:**
  - API returns HTTP 504 / 502 with structured error code (`PROVIDER_TIMEOUT`).
  - Frontend state machine transitions to `ERROR` and preserves user's session without crashing.

### Test 13: TTS Provider Upstream Failure Fallback
- **Input:** Advisor query succeeds, but subsequent `/voice/tts` synthesis fails.
- **Assertions:**
  - Text response remains 100% accessible to farmer.
  - System indicates audio is temporarily unavailable while leaving text and citations visible.

### Test 14: LLM Provider Unavailable
- **Input:** Gemini API key missing or returns HTTP 503.
- **Assertions:**
  - System falls back to offline deterministic synthesizer or clean advisory message.
  - Never serves arbitrary unsupported hallucinated data.

### Test 15: Mandi Upstream Unavailable (Cache Fallback)
- **Input:** Live Agmarknet API endpoint unreachable.
- **Assertions:**
  - Retrieval service serves verified `production_cached` records.
  - Response clearly displays badge: `"Official source • Cached data"`.
  - Never displays cached data as live.

### Test 16: Conversation Continuity & Multi-Turn Association
- **Input:**
  - Turn 1: *"What are the critical irrigation stages for wheat?"* (`conversation_id` created).
  - Turn 2: *"And what about yellow rust?"* (passing same `conversation_id`).
- **Assertions:**
  - Both queries are linked to the same `Conversation` record in DB.
  - Turn 2 inherits `crop="Wheat"` from Turn 1.
  - Both query and response pairs are retrievable via conversation history.

### Test 17: Farmer Context Persistence
- **Input:** Request includes `farmer_context: { state: "Punjab", district: "Ludhiana", crop: "Wheat" }`.
- **Assertions:**
  - Retrieval engine applies state applicability and crop metadata filters.
  - Entities are persisted in `query_logs.extracted_entities`.

---

## 4. Live Judge Demo Script

A deterministic 4-turn interaction demonstration:

```
[TURN 1: Voice Advisory in Hindi]
Farmer: (Clicks Mic, speaks in Hindi)
"गेहूं में सिंचाई कब करनी चाहिए?"
System:
- STT transcribes to: "गेहूं में सिंचाई कब करनी चाहिए?"
- Intent: CROP_ADVISORY | Crop: Wheat
- Retrieval: ICAR-IARI Wheat Guide (Relevance 0.85)
- Grounded Answer: Highlights CRI (20-25 DAS), Tillering (40-45 DAS), Jointing, Booting, Milk, and Dough stages.
- Provenance: ICAR - Indian Agricultural Research Institute (IARI / Pusa) (Official source • Cached data)
- TTS: Synthesizes Hindi audio and automatically plays back.

[TURN 2: Follow-Up in Same Conversation]
Farmer: (Types or speaks follow-up)
"इसमें पीला रतुआ की पहचान कैसे करें?"
System:
- Uses existing conversation_id.
- Inherits crop="Wheat".
- Intent: PEST_DISEASE | Pest: Yellow Rust
- Grounded Answer: Explains linear yellow stripes on leaves, powdery yellow pustules.
- Citation: ICAR-IARI Wheat Guide.

[TURN 3: Mandi Price Query]
Farmer:
"इंदौर मंडी में गेहूं का क्या भाव है?"
System:
- Intent: MANDI_PRICE | Commodity: Wheat | Market: Indore
- Deterministic Output:
  * Commodity: Wheat
  * Market: Indore (Indore, Madhya Pradesh)
  * Variety / Grade: Lokwan / FAQ
  * Min Price: ₹2450.00 | Max Price: ₹2850.00 | Modal Price: ₹2650.00/quintal
  * Arrival Date: 2026-09-22
  * Provenance: Agmarknet (Official source • Live data)
- LLM called: NO

[TURN 4: Unsupported Out-of-Scope Query]
Farmer:
"कल का मैच किसने जीता?"
System:
- Intent: UNSUPPORTED
- Pre-LLM Gate: Abstained (YES)
- Response: "I couldn't find enough verified agricultural information in official ICAR, SAU, or government sources to answer that safely. (Query is outside the supported agricultural advisory scope.)"
- LLM called: NO
- Zero hallucination.
```

---

## 5. Verification Commands

To execute all tests and verify production readiness:

```bash
# 1. Run all backend automated tests (Unit, Service, API, and Integration)
pytest -v tests

# 2. Run Phase 5 integration test suite specifically
pytest -v tests/test_phase5_integration.py

# 3. Verify Next.js frontend production compilation
cd frontend
npm run build
```
