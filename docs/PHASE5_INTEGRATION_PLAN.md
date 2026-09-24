# Phase 5 Integration Plan: Unified End-to-End Farmer Advisory Assistant

## 1. Existing Architecture Assessment

The system has completed Phases 1 through 4 with high architectural discipline and strict data governance:

| Subsystem | Components & Status | Strengths & Capabilities | Integration Gaps to Bridge |
| :--- | :--- | :--- | :--- |
| **Backend & Core DB** | FastAPI, SQLAlchemy, PostgreSQL / Supabase, SQLite local dev fallback, 83 passing automated tests. | Strong provider abstraction, clean DTO contracts, idempotent seeding, audit logs. | Currently lacks an endpoint to fetch conversation history (`GET /api/v1/advisor/conversations/{id}`) and anonymous farmer profile endpoints. |
| **Data Ingestion** | 6 verified agricultural publications (26 chunks, 768-dim embeddings), 5 government schemes, Agmarknet mandi provider. | Strict metadata (`crop`, `state`, `season`, `growth_stage`, `topic`, `source`, `source_date`). Separate data origins (`production_live`, `production_cached`, `development_seed`). | Mandi and schemes are queried via separate endpoints as well as the central RAG advisor; frontend needs unified entry point. |
| **Voice Services** | Sarvam STT (`/api/v1/voice/stt`), Sarvam TTS (`/api/v1/voice/tts`), 10-language registry (`/api/v1/voice/languages`). | Browser `MediaRecorder` support, container header validation (RIFF/WAV, WebM, MP4/M4A), clean error codes. | Frontend currently holds disconnected voice states (`voiceState`, `advisorLoading`, `isPlayingAudio`) that can desynchronize during errors. |
| **Conversational Advisor** | 10-layer RAG orchestrator (`/api/v1/advisor/query`): Preprocessor → Intent Classifier → Context Extractor → Retrieval → Pre-LLM Gate → LLM/Deterministic Formatter → Grounding Validator → Persistence. | 100% deterministic mandi formatting, structured scheme criteria vs farmer eligibility separation, strict pre-LLM threshold (0.55), post-LLM chemical/dosage validation. | Frontend does not yet preserve farmer profile context (state, district, active crops) across queries; conversation history is not visible to farmer in UI. |
| **Frontend UI** | Next.js 16.3.5 (Turbopack), React 19, TypeScript, Vanilla CSS design tokens. | Production build clean (505ms), responsive layout, grounded answer card, citation badges with raw URLs. | Current UI is slightly split across multiple diagnostic tabs (`mandi`, `schemes`, `sources`). Needs simplification into a mobile-first, farmer-centric flow: **Language → Mic → Question → Answer → Listen**. |

---

## 2. Integration Architecture

The Phase 5 integration brings together the voice pipeline, text pipeline, conversational advisor, and farmer context into a single unified loop.

```
+----------------------------------------------------------------------------------------------------+
|                                    FARMER INTERACTION LAYER (FRONTEND)                             |
|                                                                                                    |
|  [Language Selector]  --->  [Microphone Button]  OR  [Text Input Box]  --->  [Farmer Context Sheet] |
|   (hi-IN, te-IN, etc.)       (Browser MediaRecorder)    (Native Keyboard)     (State, District, Crop) |
+------------------------------------+-------------------------+-------------------------------------+
                                     |                         |
                               [Audio Upload]            [Text Query]
                                     |                         |
                                     v                         |
                     +-------------------------------+         |
                     |  POST /api/v1/voice/stt       |         |
                     |  - Sarvam STT (Saaras model)  |         |
                     |  - Audio container validation |         |
                     +---------------+---------------+         |
                                     |                         |
                              [Transcript]                     |
                                     |                         |
                                     +------------+------------+
                                                  |
                                                  v
                               +-------------------------------------+
                               | POST /api/v1/advisor/query          |
                               | (Unified Conversational Endpoint)   |
                               | - query: string                     |
                               | - language: string                  |
                               | - conversation_id: string           |
                               | - farmer_context: FarmerContextDTO  |
                               +------------------+------------------+
                                                  |
                                                  v
         +-------------------------------------------------------------------------+
         |                    10-LAYER ADVISOR ORCHESTRATOR                        |
         | 1. Query Normalization (Unicode NFKC, Devanagari/Telugu preserved)      |
         | 2. Strict Intent Classification (CROP, PEST, MANDI, SCHEME, UNSUPPORTED) |
         | 3. Context Extraction (Zero-hallucination entity matcher)               |
         | 4. Specialized Retrieval (Vector 768-dim, Mandi cache, Schemes)         |
         | 5. Pre-LLM Evidence Validation & Abstention Gate (Threshold >= 0.55)    |
         | 6. Deterministic Formatter (Mandi prices, Government schemes)           |
         | 7. Grounded LLM Provider (Gemini 3.8 Flash / Offline Mock Synthesizer)  |
         | 8. Post-LLM Grounding & Dosage Validator                                |
         | 9. Provenance & Citation Assembly (Raw URLs, Live/Cached badges)       |
         | 10. Database Persistence (conversations, query_logs, response_logs)     |
         +----------------------------------------+--------------------------------+
                                                  |
                                                  v
                                      [AdvisorQueryResponse]
                                                  |
                                                  v
                               +-------------------------------------+
                               | POST /api/v1/voice/tts              |
                               | (Optional / Triggered Voice Output) |
                               | - Sarvam TTS (Bulbul model)         |
                               | - Regional language voice synthesis |
                               +------------------+------------------+
                                                  |
                                                  v
                                 [Base64 WAV Audio -> Auto Playback]
```

### Key Integration Guarantees:
1. **Convergence**: Both voice and text inputs converge on `POST /api/v1/advisor/query`. No alternate backdoor routes exist.
2. **Language Invariance**: The farmer's chosen language flows through Frontend → STT → Advisor Query → Response Text → TTS.
3. **Graceful Degradation**: If TTS synthesis fails, the textual advisory response and citations remain fully visible and usable.
4. **Context Consistency**: State, district, and crop preferences stored in the farmer's session are automatically merged with on-the-fly extracted query entities.

---

## 3. Frontend State Machine

To eliminate state desynchronization and race conditions, the frontend UI adheres to an explicit finite state machine (FSM).

```
                      +-------------------+
                      |       IDLE        |<-----------------------------+
                      +---------+---------+                              |
                                |                                        |
            [Click Mic]         |         [Type / Submit Text]           |
          +---------------------+---------------------+                  |
          |                                           |                  |
          v                                           v                  |
   +--------------+                            +--------------+          |
   |  RECORDING   |                            |  TEXT_INPUT  |          |
   +------+-------+                            +------+-------+          |
          | [Stop Mic / Auto-timeout]                 | [Submit Button]  |
          v                                           v                  |
   +--------------+                            +----------------+        |
   |  UPLOADING   |                            | SUBMITTING_TEXT|        |
   +------+-------+                            +------+---------+        |
          | [Bytes sent]                              |                  |
          v                                           |                  |
   +--------------+                                   |                  |
   | TRANSCRIBING |                                   |                  |
   +------+-------+                                   |                  |
          | [STT Success]                             |                  |
          v                                           |                  |
   +--------------+                                   |                  |
   | READY_TO_ASK |-----------------------------------+                  |
   +--------------+                                                      |
          | [Auto-forward or Confirm]                                    |
          v                                                              |
   +--------------+                                                      |
   |   THINKING   |<-----------------------------------------------------+
   +------+-------+                                                      |
          | [Advisor Success]                                            |
          v                                                              |
   +--------------+       [Click Listen / Auto-TTS]       +--------------+
   | ANSWER_READY |-------------------------------------->|   SPEAKING   |
   +------+-------+                                       +------+-------+
          |                                                      |
          | [New Query]                                          | [Audio Ends / Pause]
          +--------------------------> IDLE <--------------------+
                                       ^
                                       | [Dismiss / Retry]
                               +-------+-------+
                               |     ERROR     |
                               +---------------+
                   (Entered from any state on network / validation failure)
```

### State Definitions and Transition Rules

| State | Allowed User Actions | Disabled Controls | Transitions To |
| :--- | :--- | :--- | :--- |
| **IDLE** | Click Mic, Type Text, Select Language, Edit Profile | Stop Mic, Audio Controls | `RECORDING` (mic click), `TEXT_INPUT` (keyboard input) |
| **RECORDING** | Click Stop Mic, Cancel Recording | Language change, Text input, Ask button | `UPLOADING` (on stop), `IDLE` (on cancel), `ERROR` (on mic fail) |
| **UPLOADING** | Cancel upload | All inputs | `TRANSCRIBING` (bytes sent), `ERROR` (network drop) |
| **TRANSCRIBING** | None (shows spinner & wave animation) | All inputs | `READY_TO_ASK` (STT success), `ERROR` (STT failure) |
| **READY_TO_ASK** | Edit transcribed text, Click "Ask", Re-record | Language change | `THINKING` (submit), `RECORDING` (re-record) |
| **TEXT_INPUT** | Type characters, Click "Ask", Clear text | Mic disabled while typing | `SUBMITTING_TEXT` (click ask), `IDLE` (if input cleared) |
| **SUBMITTING_TEXT**| None (shows button loading state) | All inputs | `THINKING` |
| **THINKING** | Cancel query | All inputs | `ANSWER_READY` (200 OK), `ERROR` (500/timeout) |
| **ANSWER_READY** | Click "Listen", Ask follow-up question, Scroll citations | None | `SPEAKING` (listen click), `RECORDING` / `TEXT_INPUT` (follow-up) |
| **SPEAKING** | Pause Audio, Stop Audio, Replay | Language change | `ANSWER_READY` (audio ended / stopped) |
| **ERROR** | Click "Try Again", Dismiss error, Use text fallback | None | `IDLE` (dismiss / retry) |

---

## 4. API Flow Specification

### 4.1 Voice Query Flow
1. **Frontend**: Records audio via `MediaRecorder` (`audio/webm;codecs=opus` or `audio/wav`).
2. **Frontend → Backend** (`POST /api/v1/voice/stt`):
   - Headers: `Content-Type: multipart/form-data`
   - Form parameters: `audio_file` (binary blob), `language` (e.g. `hi-IN`).
3. **Backend**:
   - `validate_audio_payload()`: checks size $\le 10\text{ MB}$, duration, valid header bytes.
   - Calls `stt_provider.transcribe(audio_bytes, language_hint="hi-IN")`.
   - Returns `STTResponse`: `{ transcript: "गेहूं में सिंचाई कब करनी चाहिए?", detected_language: "hi-IN", confidence: 0.96 }`.
4. **Frontend → Backend** (`POST /api/v1/advisor/query`):
   - Payload:
     ```json
     {
       "query": "गेहूं में सिंचाई कब करनी चाहिए?",
       "language": "hi-IN",
       "conversation_id": "4b68e91d-...",
       "farmer_context": {
         "crop": "Wheat",
         "state": "Punjab",
         "district": "Ludhiana"
       }
     }
     ```
5. **Backend Advisor Orchestrator**:
   - Executes 10-layer pipeline and logs query + response to DB.
   - Returns `AdvisorQueryResponse` with grounded answer and citations.
6. **Frontend → Backend** (`POST /api/v1/voice/tts`):
   - Payload: `{ "text": response_text, "language": "hi-IN", "speaker": "meera" }`.
   - Returns `TTSResponse`: `{ "audio_base64": "...", "duration_seconds": 4.2 }`.
7. **Frontend**: Plays back base64 WAV stream via HTML5 Audio.

### 4.2 Text Query Flow
1. **Farmer**: Enters query directly in regional script or English.
2. **Frontend → Backend** (`POST /api/v1/advisor/query`):
   - Identical payload structure as step 4 above.
   - Bypasses STT step.
3. **Response & TTS**: Identical steps 5–7.

---

## 5. Conversation Flow & Schema Continuity

### 5.1 Existing Schema Compatibility
Inspection of `backend/app/models/models.py` confirms that the current tables already support:
- `conversations`: Primary key `id` (UUID), `farmer_id` (FK), `title`, `created_at`, `updated_at`.
- `query_logs`: `id`, `conversation_id` (FK), `farmer_id` (FK), `input_channel` (`'voice'` or `'text'`), `detected_language`, `raw_transcript`, `classified_intent`, `extracted_entities`, `created_at`.
- `response_logs`: `id`, `query_id` (FK), `response_text`, `is_grounded`, `confidence_score`, `disclaimer_applied`, `retrieved_sources`, `latency_breakdown_ms`.

### 5.2 Conversation Continuity Rules
1. **Session-Level `conversation_id`**: Generated on the client on first query (or returned by the backend on initial query) and stored in `sessionStorage`.
2. **Follow-Up Handling**: All subsequent questions within that farmer interaction pass the existing `conversation_id`.
3. **Backend Association**: In `AdvisorOrchestrator._persist_log()`, if `conv_id` already exists, the new `QueryLog` and `ResponseLog` are appended to the existing `Conversation` record.
4. **Context Inheritance**: If the previous query in the same conversation established `crop="Wheat"` or `market="Indore"`, and the follow-up is an ellipsis (e.g. *"और खाद कितनी देनी है?"*), the context extractor inherits the active crop context from prior turns in that conversation.
5. **Conversation History API**: Add a minimal read-only endpoint:
   - `GET /api/v1/advisor/conversations/{conversation_id}`: Returns list of query-response pairs ordered by `created_at ASC`.

---

## 6. Farmer Context Strategy

Small and marginal farmers should never be forced through cumbersome multi-step registration or passwords.

### 6.1 Profile Fields
- `farmer_id`: Client-generated UUID stored in `localStorage` (`farmer_session_id`).
- `preferred_language`: Defaults to `hi-IN`, selectable from the primary language bar.
- `state`: Optional regional filter (e.g. `Madhya Pradesh`, `Punjab`, `Telangana`).
- `district`: Optional local mandi/crop filter (e.g. `Indore`, `Ludhiana`, `Warangal`).
- `crops`: List of active crops (e.g. `["Wheat", "Paddy"]`).

### 6.2 Storage & Propagation
1. **Client Storage**: Persisted in `localStorage.getItem("farmer_profile")`.
2. **UI Entry Point**: Minimal "My Farm / मेरा खेत" slide-down drawer or compact pill header:
   - "📍 Indore, Madhya Pradesh • 🌾 Wheat" (1-tap to edit).
3. **Payload Injection**: Automatically serialized into `farmer_context: FarmerContextDTO` on every `POST /api/v1/advisor/query`.
4. **Zero Hallucination Rule**: If a field is empty/unset, the backend context extractor does not guess or infer it. It operates in general/national scope (`All-India`).

---

## 7. Error Handling & Safe Abstention Strategy

| Failure Scenario | Backend Behavior | Frontend User Experience |
| :--- | :--- | :--- |
| **Microphone Permission Denied** | N/A (client-side) | Clear alert: *"Microphone access is needed for voice queries. Please enable it in browser settings or type your question below."* Directs to text input. |
| **Empty or Inaudible Audio** | `validate_audio_payload` rejects with `AUDIO_EMPTY` (HTTP 400). | *"No voice detected. Please speak closer to the microphone and try again."* |
| **STT Upstream Timeout / Auth Error** | Catches `TimeoutError` or `PermissionError`, returns HTTP 504 / 502 with structured error code. | *"Speech recognition is temporarily unavailable. Please type your question."* Focus moves to text box with query preserved. |
| **Unsupported Out-of-Scope Query** | Intent classifier returns `UNSUPPORTED`; relevance is 0.0; pre-LLM gate abstains (`abstained=True`, `llm_called=False`). | Amber advisory badge: *"This question is outside agricultural advisory scope. Please ask about crop cultivation, pest control, mandi rates, or government schemes."* |
| **Insufficient Agricultural Evidence** | Relevance score $< 0.55$; pre-LLM gate abstains (`abstained=True`, `llm_called=False`). | Amber shield badge: *"Official ICAR/government records do not have verified guidance for this specific query. Please consult your local Krishi Vigyan Kendra (KVK)."* |
| **Gemini LLM Rate Limit / Downtime** | Fallback to offline mock synthesizer or graceful HTTP 503 error; never returns ungrounded hallucination. | Informative notice: *"Advisory service is experiencing high traffic. Please try again in a few moments."* |
| **Mandi Price Upstream Unavailable** | Fallback to `production_cached` records with `"Official source • Cached data"` badge; if no cache exists, abstains. | Renders cached price clearly labeled with arrival date, or notes no recent verified prices for that mandi. |
| **TTS Upstream Synthesis Failure** | Returns HTTP 502 / 504 on `/voice/tts`. | **Does not destroy text answer.** The grounded answer and citations remain fully readable. A subtle note says: *"Audio playback unavailable. Please read the response above."* |

---

## 8. Security & Trust Architecture

1. **Strict Server-Side Credential Isolation**:
   - `GEMINI_API_KEY`, `SARVAM_API_KEY`, `DATA_GOV_IN_API_KEY`, and `DATABASE_URL` remain strictly server-side in backend `.env`.
   - The Next.js frontend has zero access to external provider keys. Only `NEXT_PUBLIC_BACKEND_URL` is exposed.
2. **Audio Upload Validation**:
   - Size limit: Max 10 MB.
   - Duration limit: Max 60 seconds.
   - Container magic bytes validation: RIFF header for WAV, EBML header for WebM, ftyp header for M4A. Reject any executable or mismatched payload before processing.
3. **CORS & Rate Limiting**:
   - FastAPI CORS middleware restricted to designated frontend origins in production.
   - Rate limiting on `/voice/stt` and `/advisor/query` to prevent Denial-of-Service attacks.
4. **No Sensitive Farmer PII**:
   - Profiles contain only agronomic context (state, district, crop).
   - Aadhaar numbers, bank account numbers, or passwords are never requested or stored.
5. **Raw Official URLs**:
   - All `official_url` citations are validated absolute HTTPS URLs from official government domains (`.gov.in`, `.nic.in`, `.res.in`).

---

## 9. Test Strategy (Phase 5)

A comprehensive 17-point test suite will be implemented in `tests/test_phase5_integration.py` and frontend test suites:

1. **Text → Advisor Pipeline**: Verifies text query through full 10-layer orchestrator.
2. **Voice → STT → Advisor Pipeline**: Verifies audio upload, transcription, and transition to advisor.
3. **Advisor → TTS Pipeline**: Verifies advisor response text conversion to regional WAV audio.
4. **Full Voice Round Trip**: Audio in → STT → RAG → TTS → Audio out.
5. **Hindi Flow**: Complete advisory interaction in `hi-IN` with Devanagari script.
6. **Telugu Regional Flow**: Complete advisory interaction in `te-IN` with Telugu script.
7. **Mandi Query**: Structured deterministic formatting, arrival date, and provenance badge.
8. **Government Scheme Query**: PM-KISAN/KCC retrieval with explicit criteria vs eligibility distinction.
9. **Agricultural RAG Query**: Yellow stem borer query with grounded dosages and pest control measures.
10. **Unsupported Query**: Cricket / movie query with immediate safe abstention.
11. **Insufficient Evidence**: Un-ingested query safely triggering abstention without LLM hallucination.
12. **STT Upstream Failure**: Graceful error handling and fallback to text input.
13. **TTS Upstream Failure**: Preservation of textual response when audio synthesis fails.
14. **LLM Provider Unavailable**: Graceful fallback without crashing the orchestrator.
15. **Mandi Upstream Unavailable**: Fallback to verified cached mandi records.
16. **Conversation Continuity**: Reusing `conversation_id` across turns and verifying log persistence.
17. **Farmer Context Persistence**: Propagation of `state`, `district`, and `crop` through the retrieval pipeline.

---

## 10. Step-by-Step Implementation Sequence

Phase 5 will be executed in 4 controlled sub-phases:

```
+-------------------------------------------------------------------------------+
| Step 1: Backend Integration Enhancements                                      |
| - Add GET /api/v1/advisor/conversations/{id} to retrieve conversation history  |
| - Support input_channel ("voice" | "text") in AdvisorQueryRequest             |
| - Ensure conversation turn context carries active crop/market                 |
+---------------------------------------+---------------------------------------+
                                        |
                                        v
+-------------------------------------------------------------------------------+
| Step 2: Mobile-First Farmer UI Redesign                                       |
| - Implement explicit frontend State Machine (IDLE -> RECORDING -> ... )       |
| - Language selector header (Hindi, Telugu, Tamil, Marathi, Kannada, English)  |
| - Large primary Microphone button with pulse ring & duration counter          |
| - Slide-down / modal Farmer Context drawer (State, District, Active Crops)    |
| - Unified conversation thread displaying farmer query + grounded answer card  |
| - Audio player bar with Play/Pause/Replay and accessible text fallback        |
+---------------------------------------+---------------------------------------+
                                        |
                                        v
+-------------------------------------------------------------------------------+
| Step 3: End-to-End Automated Integration Test Suite                           |
| - Implement tests/test_phase5_integration.py covering all 17 scenarios        |
| - Verify 100+ backend tests pass with pytest                                  |
| - Verify Next.js production build succeeds with 0 lint/type errors            |
+---------------------------------------+---------------------------------------+
                                        |
                                        v
+-------------------------------------------------------------------------------+
| Step 4: Full System Verification & Live Judge Demo Walkthrough                |
| - Execute 3-step Judge Demo scenario:                                         |
|   Turn 1: Voice in Hindi -> Wheat irrigation advisory -> Hindi TTS            |
|   Turn 2: Follow-up question in same conversation                             |
|   Turn 3: Indore mandi wheat price query with deterministic formatting        |
|   Turn 4: Unsupported question demonstrating safe abstention                  |
+-------------------------------------------------------------------------------+
```

---

## 11. Files Expected to Change

### Backend Files
- `backend/app/schemas/advisor.py`:
  - Add `input_channel: Optional[str] = "text"` to `AdvisorQueryRequest`.
  - Add `ConversationHistoryDTO` and `ConversationTurnDTO` for thread view.
- `backend/app/api/v1/advisor.py`:
  - Add `GET /conversations/{conversation_id}` endpoint.
- `backend/app/services/advisor_orchestrator.py`:
  - Record `input_channel` properly into `QueryLog`.
  - Support multi-turn context carry-over from preceding query in the same conversation.

### Frontend Files
- `frontend/src/app/page.tsx`:
  - Implement the complete state machine (`VoiceState`).
  - Streamline the UI into a focused mobile-first farmer flow.
  - Implement conversation message thread.
  - Add Farmer Context drawer.
- `frontend/src/app/globals.css`:
  - Mobile-first responsive touch target styling, recording pulse animations, high-contrast readable typography.

### Documentation & Test Files
- `docs/PHASE5_INTEGRATION_PLAN.md` (this document)
- `docs/PHASE5_TEST_PLAN.md` (test specifications)
- `tests/test_phase5_integration.py` (new integration tests)

---

## 12. Database Changes (Smallest Migration Strategy)

**Result of Schema Assessment: ZERO SCHEMA MIGRATIONS REQUIRED.**

The existing Phase 1–2 PostgreSQL / Supabase schema already includes:
- `farmer_profiles` with `session_id`, `preferred_language`, `state`, `district`, `land_holding_acres`.
- `farmer_crops` with `crop_name`, `variety`, `stage`.
- `conversations` with `id`, `farmer_id`, `title`, `created_at`.
- `query_logs` with `id`, `conversation_id`, `farmer_id`, `input_channel`, `raw_transcript`, `classified_intent`, `extracted_entities`.
- `response_logs` with `query_id`, `response_text`, `is_grounded`, `retrieved_sources`, `latency_breakdown_ms`.

All required Phase 5 features are fully supported by the existing tables and foreign keys. No `ALTER TABLE` or database downtime is necessary.

---

## 13. Risk Management & Mitigations

| Risk | Impact | Mitigation |
| :--- | :--- | :--- |
| **Browser Microphone Denial** | Farmer cannot speak queries | Immediate friendly notification; UI gracefully focuses the text box so farmer can type in regional script. |
| **Network Latency on 2G/3G** | Stalled UI or timeout | Visual progress indicator with stage-by-stage feedback (*"Uploading audio..."* → *"Transcribing..."* → *"Consulting agricultural records..."*); 15s timeout with retry button. |
| **Audio Desynchronization** | Audio playing while user tries to record another query | State machine strictly halts active `HTMLAudioElement` before permitting new recording or text submission. |
| **Regional Language Font Rendering** | Distorted Indian script display on older Android devices | Use standard Google Noto Sans fonts for Devanagari, Telugu, Tamil, and Gurmukhi with system font fallbacks. |

---

## 14. Rollback Strategy

1. **Git Isolation**: All Phase 5 work will be developed in small, verified atomic commits.
2. **Backward-Compatible Backend**: All schema and endpoint additions are strictly additive; existing Phase 4 `/api/v1/advisor/query` and Phase 3 `/api/v1/voice/*` remain 100% backward compatible.
3. **Instant Revert**: If the frontend mobile-first UI requires rollback, `frontend/src/app/page.tsx` can be restored immediately from the Phase 4 approved snapshot without affecting backend stability.

---

## 15. Definition of Done (DoD)

Phase 5 will be considered complete when:
- [ ] End-to-end voice query pipeline functions smoothly: Record Audio → STT → RAG → Response → TTS Playback.
- [ ] Text query pipeline functions identically over the same Advisor API.
- [ ] Language propagation is consistent across UI, STT, Advisor, Response, and TTS.
- [ ] Farmer context (state, district, crop) is persisted in local session and utilized by retrieval.
- [ ] Follow-up questions remain associated with the same `conversation_id`.
- [ ] Mandi price queries produce deterministic structured tables with provenance badges.
- [ ] Government scheme queries cleanly separate documented criteria from individual farmer eligibility.
- [ ] Safe abstention triggers reliably for unsupported or ungrounded queries.
- [ ] TTS failure does not destroy the readable text answer.
- [ ] Mobile-first UI adheres to the LANGUAGE → MIC → QUESTION → ANSWER → LISTEN workflow.
- [ ] All 17 integration test scenarios pass in automated test suite.
- [ ] Total automated test count exceeds 95 tests, all passing.
- [ ] Production build (`npm run build`) compiles with zero TypeScript errors and zero warnings.
