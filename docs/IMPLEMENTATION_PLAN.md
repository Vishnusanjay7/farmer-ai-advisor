# Step-by-Step Implementation Roadmap

## 1. Overview & Verification Strategy
This roadmap breaks the project into sequential, highly testable, and independently verifiable phases. Each task has defined acceptance criteria and automated/manual verification tests.

```
Phase 1: Project Setup & Core Scaffolding
   │
Phase 2: Database Schema & Knowledge Base Seeding
   │
Phase 3: Provider Layer (STT, TTS, LLM, Embeddings, Mandi, Schemes)
   │
Phase 4: Backend Pipeline & Grounded Guardrail Engine
   │
Phase 5: Mobile-First Next.js Frontend
   │
Phase 6: End-to-End Integration, Security & Deployment Readiness
```

---

## 2. Detailed Phases & Verifiable Tasks

### Phase 1: Project Setup & Core Scaffolding
- [ ] **Task 1.1: Backend Structure Initialization**
  - Create `backend/` directory with Python virtual environment, `pyproject.toml`, `requirements.txt`.
  - Install FastAPI, Pydantic v2, Uvicorn, httpx, SQLAlchemy, asyncpg, pgvector, pytest.
  - Setup core config (`backend/app/core/config.py`) loading `.env` with validation.
  - *Verification:* Run `pytest` and start `uvicorn main:app --reload` verifying `/api/v1/health` returns `{"status": "healthy"}`.
- [ ] **Task 1.2: Frontend Initialization**
  - Scaffold Next.js TypeScript app in `frontend/` with App Router.
  - Configure `globals.css` with mobile-first custom CSS design tokens (accessible colors, high-contrast, typography).
  - *Verification:* `npm run build` succeeds with zero TypeScript errors.

---

### Phase 2: Database Schema & Knowledge Base Ingestion [COMPLETED]
- [x] **Task 2.1: Supabase / PostgreSQL Schema Definition**
  - Migrations `20260922000000_initial_schema.sql` and `20260922000001_phase2_provenance_and_chunking.sql`.
  - UUID PKs, pgvector 768-dim embeddings, HNSW index, foreign keys, timestamps, and `data_origin` separation.
- [x] **Task 2.2: Government Scheme Seeding**
  - `scripts/seed_government_schemes.py` seeds PM-KISAN, PMFBY, KCC, Soil Health Card, and PMKSY.
  - Idempotent execution verified; sync audit log created.
- [x] **Task 2.3: ICAR / Agronomic Document Chunking & Embeddings**
  - Authoritative Package of Practices from ICAR (IIRR, IARI, CICR) and SAUs (ANGRAU, PAU, UAS Bangalore).
  - Deterministic chunking (`AgronomicChunker`) with paragraph preservation and SHA-256 deduplication.
  - 768-dimensional embeddings generated and indexed.
- [x] **Task 2.4: Mandi Price Fetcher & Sync Worker**
  - `AgmarknetMandiProvider` with live Data.gov.in fetch, strict date parsing, database caching, and fallback.
  - Strict distinction between arrival date and fetched timestamp.
- [x] **Task 2.5: Phase 2 Read-Only API Endpoints**
  - Implemented `GET /api/v1/mandi/prices`, `GET /api/v1/schemes/search`, `GET /api/v1/agriculture/sources`, `GET /api/v1/agriculture/topics`.
  - 27 automated tests passing.

---

### Phase 3: Regional Indian Language Voice Services [COMPLETED]
- [x] **Task 3.1: Language Registry & Centralized Configuration**
  - Implemented `backend/app/core/languages.py` supporting 11 regional languages (`hi-IN`, `te-IN`, `ta-IN`, `mr-IN`, `kn-IN`, `bn-IN`, `gu-IN`, `ml-IN`, `pa-IN`, `or-IN`, `en-IN`).
  - Mapped STT (`saaras:v3`) and TTS (`bulbul:v3`) provider models and regional speaker voices.
- [x] **Task 3.2: Audio Validation Service**
  - Implemented `backend/app/services/audio_validator.py`.
  - Enforced 15 MB limit, binary magic byte container validation (RIFF/WAV, WebM, MP3 ID3/Sync, OGG, M4A ftyp), non-empty validation.
- [x] **Task 3.3: Official Sarvam STT & TTS Providers**
  - Implemented `SarvamSTTProvider` (`POST https://api.sarvam.ai/speech-to-text`) using `saaras:v3` and `SarvamTTSProvider` (`POST https://api.sarvam.ai/text-to-speech`) using `bulbul:v3`.
  - Implemented `MockSTTProvider` and `MockTTSProvider` strictly isolated for automated testing.
  - Strict error handling for missing keys, network timeouts, downstream errors, and unsupported languages.
- [x] **Task 3.4: Voice REST API Endpoints**
  - Implemented `POST /api/v1/voice/stt`, `POST /api/v1/voice/tts`, and `GET /api/v1/voice/languages`.
  - Added dependency injection for providers, sanitized logging, and typed Pydantic DTOs.
- [x] **Task 3.5: Frontend Real Voice Interaction Layer**
  - Integrated browser `MediaRecorder` API with complete state transitions: `IDLE` -> `RECORDING` -> `UPLOADING` -> `TRANSCRIBING` -> `TRANSCRIBED` -> `SYNTHESIZING` -> `PLAYING`.
  - Added native HTML5 audio playback and real-time status banners.
- [x] **Task 3.6: Verification & Testing**
  - 55/55 automated tests passing (`tests/test_audio_validator.py`, `tests/test_stt_provider.py`, `tests/test_tts_provider.py`, `tests/test_languages.py`, `tests/test_voice_api.py`).
  - Next.js production frontend build clean with zero errors.

---

### Phase 4: Conversational Agricultural RAG Intelligence [COMPLETED]
- [x] **Task 4.1: Query Preprocessing, Intent & Context Extraction**
  - Implemented `query_preprocessor.py` (Unicode NFKC, native script and ID preservation).
  - Implemented `intent_classifier.py` (`CROP_ADVISORY`, `PEST_DISEASE`, `MANDI_PRICE`, `GOVERNMENT_SCHEME`, `UNSUPPORTED`, `UNKNOWN`).
  - Implemented `context_extractor.py` extracting crops, varieties, states, districts, and pests with zero hallucination.
- [x] **Task 4.2: Specialized Retrieval by Intent & 768-Dim Vector Engine**
  - Implemented `retrieval_service.py` preserving existing 768-dim stored embeddings.
  - Hybrid scoring (dense vector similarity + stop-word filtered token overlap).
  - Mandi retrieval strictly filters for `production_live` and `production_cached` (rejects `development_seed`).
  - Government scheme structured search matching code, criteria, and portal URLs.
- [x] **Task 4.3: Grounding Validation & Safety Heuristic**
  - Implemented `grounding_validator.py` with pre-LLM threshold gating ($\ge 0.55$) and post-LLM numeric/dosage safety checks.
  - Generates standardized, multilingual abstentions for unverified or out-of-scope requests.
- [x] **Task 4.4: LLM Provider & Pipeline Orchestration**
  - Implemented `GeminiLLMProvider` targeting official `gemini-3.8-flash` production model.
  - Implemented `MockLLMProvider` strictly for local testing.
  - Built `AdvisorOrchestrator` tying together all 10 layers with conversation logging in `conversations`, `query_logs`, `response_logs`.
- [x] **Task 4.5: REST API Endpoint & Minimal Frontend Integration**
  - Implemented `POST /api/v1/advisor/query`.
  - Wired STT voice transcript to "Ask Advisor" flow with Grounded Advisory card in `frontend/src/app/page.tsx`.
- [x] **Task 4.6: Automated Testing & Scenario Verification**
  - 83/83 automated tests passing in 4.03s.
  - 6/6 deterministic verification scenarios recorded with all 12 required fields.
  - Next.js production build passing with 0 errors.

---

### Phase 5: Mobile-First Conversational UI & Full System Integration [COMPLETED]
- [x] **Task 5.1: 11-State Finite State Machine Frontend**
  - Implemented explicit state machine in `frontend/src/app/page.tsx` (`IDLE`, `RECORDING`, `UPLOADING`, `TRANSCRIBING`, `READY_TO_ASK`, `THINKING`, `ANSWER_READY`, `SPEAKING`, `ERROR`, `TEXT_INPUT`, `SUBMITTING_TEXT`).
  - Guards against invalid simultaneous operations.
- [x] **Task 5.2: Farmer Context Drawer & Language Propagation**
  - LocalStorage-backed state, district, and crop preferences.
  - Multi-lingual selection header seamlessly passed to STT, Advisor query, and TTS.
- [x] **Task 5.3: Main Advisory Conversational View**
  - Renders user voice transcript / text query and grounded response with verified citations and provenance badges.
  - Audio player bar with Play/Pause/Replay and safe text fallback.
- [x] **Task 5.4: Conversation Continuity & Multi-Turn Association**
  - Session-level `conversation_id` preservation.
  - Multi-turn context inheritance in `AdvisorOrchestrator`.
  - Added `GET /api/v1/conversations/{conversation_id}` endpoint.
- [x] **Task 5.5: End-to-End Integration Verification**
  - Implemented 17 approved integration test scenarios in `tests/test_phase5_integration.py`.
  - 100/100 automated tests passing. Next.js production build passing.

---

### Phase 6: End-to-End Testing, Security & Deployment Readiness
- [ ] **Task 6.1: Comprehensive Guardrail & Safety Suite**
  - Run automated test suite verifying:
    1. Zero unverified pesticide dosages.
    2. Refusal message displayed when knowledge is absent.
    3. Mandi dates clearly indicated as live vs cached.
    4. Unsupported audio formats handled cleanly with user-friendly error messages.
- [ ] **Task 6.2: Performance & Latency Benchmarks**
  - Benchmark voice processing pipeline latency under 3.5 seconds.
  - Optimize audio payloads (e.g. Opus/WebM encoding) and backend async streaming.
- [ ] **Task 6.3: Production Deployment Configuration**
  - Backend `Dockerfile` and production `uvicorn` configuration.
  - Frontend production build verification (`npm run build`).
  - Documentation and `.env.example` verification.
