# System Architecture & Technical Design

> **Implementation Status (Phase 5 Complete)**: Full end-to-end integration complete. Converged Voice and Text pipelines on the 10-layer Conversational Advisor API, multi-turn conversation continuity with context inheritance, mobile-first 11-state FSM frontend, deterministic mandi and scheme formatting, safe abstention without hallucination, 100 passing automated tests, and clean static Next.js build.

---

## 1. High-Level Architectural Pipeline

```
                                  ┌────────────────────────┐
                                  │      Client Layer      │
                                  │  (Next.js Mobile-First) │
                                  └───────────┬────────────┘
                                              │  HTTPS / WebSockets / Audio
                                              ▼
                                  ┌────────────────────────┐
                                  │      API Gateway       │
                                  │   (FastAPI Backend)    │
                                  └───────────┬────────────┘
                                              │
         ┌────────────────────────────────────┼────────────────────────────────────┐
         ▼                                    ▼                                    ▼
┌─────────────────┐                  ┌─────────────────┐                  ┌─────────────────┐
│  Voice Pipeline │                  │ Context & Intent│                  │ Retrieval Engine│
│ (Sarvam STT/TTS)│                  │ Extractor Engine│                  │ (pgvector + SQL)│
│   [Phase 3]     │                  │    [Phase 4]    │                  │    [Phase 4]    │
└─────────────────┘                  └─────────────────┘                  └────────┬────────┘
                                                                                   │
                                              ┌────────────────────────────────────┴────────┐
                                              ▼                                             ▼
                                     ┌──────────────────┐                         ┌───────────────────┐
                                     │  PostgreSQL /    │                         │  External Gov     │
                                     │  Supabase Store  │                         │  Data Sync APIs   │
                                     │  (pgvector RAG)  │                         │  (Data.gov.in)    │
                                     │   [Phase 1 & 2]  │                         │    [Phase 2]      │
                                     └──────────────────┘                         └───────────────────┘
```

---

## 2. Core Safety & Grounding Policy

1. **Grounded Verification Standard:**
   - **No unsupported factual claim may be presented as verified.**
   - Agricultural factual responses must be grounded strictly in authoritative retrieved sources (ICAR, SAU, Agmarknet, myScheme).
   - The system must abstain and communicate transparently when sufficient official evidence is unavailable.
2. **Crop & Knowledge Extensibility:**
   - The knowledge architecture is NOT constrained to a fixed set of crops.
   - The system supports arbitrary crop types, agro-climatic zones, and regions through extensible metadata attributes:
     - `crop`, `state`, `language`, `season`, `growth_stage`, `topic`, `source`, `source_date`, and `updated_at`.
3. **Strict Separation of Data Origins:**
   - Development mock data, cached data, and live production data must NEVER be conflated.
   - The database schema and DTO layer enforce a typed `data_origin` field:
     - `production_live`: Directly fetched from authoritative source within freshness window.
     - `production_cached`: Verified authoritative record preserved with clear reporting date/timestamp.
     - `development_seed`: Local developer fixtures strictly for testing and never presented to users as authoritative.
   - The UI explicitly displays status tags and freshness dates for all data.

---

## 3. Implemented Monorepo Structure

```
farmer-ai-advisor/
├── .env.example                     # Environment template (no secrets)
├── .gitignore                       # Git exclusions for python, node, next
├── docs/                            # Living design and architecture documentation
│   ├── PRODUCT_SPEC.md
│   ├── ARCHITECTURE.md              # (Updated for Phase 1)
│   ├── DATABASE.md                  # (Updated for Phase 1)
│   ├── API_SPEC.md                  # (Updated for Phase 1)
│   ├── RAG_DESIGN.md
│   ├── DATA_SOURCES.md
│   └── IMPLEMENTATION_PLAN.md
│
├── backend/                         # FastAPI Backend Application (Implemented in Phase 1)
│   ├── requirements.txt             # Python dependencies
│   ├── app/
│   │   ├── main.py                  # FastAPI app entrypoint, CORS, logging middleware
│   │   ├── core/
│   │   │   ├── config.py            # Pydantic BaseSettings loading from .env
│   │   │   └── logging.py           # Structured logger with secret sanitization
│   │   ├── db/
│   │   │   └── session.py           # SQLAlchemy sessionmaker & engine
│   │   ├── models/
│   │   │   ├── __init__.py          # Model exports
│   │   │   └── models.py            # Core ORM models (10 tables with pgvector & UUIDs)
│   │   ├── schemas/
│   │   │   ├── __init__.py          # Schema exports
│   │   │   └── health.py            # Health check request/response models
│   │   ├── providers/
│   │   │   ├── __init__.py          # Provider exports
│   │   │   └── base.py              # Abstract interfaces (STT, TTS, Mandi, Scheme, LLM, Embed)
│   │   └── api/
│   │       └── v1/
│   │           ├── __init__.py      # Router aggregation
│   │           └── health.py        # GET /api/v1/health handler
│
├── frontend/                        # Next.js App Router Application (Implemented in Phase 1)
│   ├── package.json
│   ├── tsconfig.json
│   ├── next.config.ts
│   └── src/
│       └── app/
│           ├── layout.tsx           # SEO metadata and mobile viewport setup
│           ├── globals.css          # Vanilla CSS design tokens (tactile, mobile-first)
│           └── page.tsx             # Interactive shell with live backend connection probe
│
├── supabase/                        # Database Migrations (Implemented in Phase 1 & 2)
│   └── migrations/
│       ├── 20260922000000_initial_schema.sql # Complete 10-table schema with pgvector
│       └── 20260922000001_phase2_provenance_and_chunking.sql # Provenance & chunking schema updates
│
└── tests/                           # Test Infrastructure (Implemented in Phase 1)
    ├── __init__.py
    ├── test_health.py               # Health & root endpoint tests
    ├── test_config.py               # Settings and default validation
    ├── test_models.py               # ORM schema, extensibility, and data origin tests
    └── test_providers.py            # Provider interface abstractions & DTO tests
```

---

## 4. Provider Layer Abstractions

All external dependencies implement clean Abstract Base Classes defined in [`backend/app/providers/base.py`](file:///c:/farmer-ai-advisor/backend/app/providers/base.py):
- `SpeechToTextProvider`: Audio transcription with language detection.
- `TextToSpeechProvider`: Speech synthesis from regional text.
- `MandiPriceProvider`: Market price retrieval with `data_origin` tagging.
- `GovernmentSchemeProvider`: Welfare scheme search and filtering.
- `LLMProvider`: Grounded answer generation with strict abstention semantics.
- `EmbeddingProvider`: Vector embedding generation.

---

## 5. Regional Voice Architecture (Phase 3 Implemented)

### 5.1 Bidirectional Voice Processing Flow

```
[STT Flow]
FARMER (Speaks in regional dialect)
   ↓
Microphone Capture (Browser MediaRecorder WebM/WAV)
   ↓
POST /api/v1/voice/stt (FastAPI Multipart Upload)
   ↓
AudioValidator (Magic byte checks, size <= 15MB, MIME inspection)
   ↓
SarvamSTTProvider (Official saaras:v3 model, api-subscription-key)
   ↓
Transcribed Text & Language Metadata (Returned to Client)

[TTS Flow]
TEXT (Agricultural response/prompt)
   ↓
POST /api/v1/voice/tts (JSON { text, language })
   ↓
Input Validation (Character length <= 2500, Language registry lookup)
   ↓
SarvamTTSProvider (Official bulbul:v3 model, regional speaker profile)
   ↓
Playable Base64 WAV Audio (Returned to Client)
   ↓
HTML5 Audio Playback / User Listen
```

### 5.2 Official Sarvam AI API Contract (March 2026 Verified)
1. **Authentication:** Secure header `api-subscription-key: <SARVAM_API_KEY>`. No credentials exist in the client/browser layer.
2. **STT Service (`saaras:v3`):**
   - Endpoint: `POST https://api.sarvam.ai/speech-to-text`
   - Encoding: `multipart/form-data` with fields `file`, `model: "saaras:v3"`, `language_code: "<bcp47>"`, `mode: "transcribe"`.
   - Response: `{"transcript": "...", "language_code": "..."}`.
3. **TTS Service (`bulbul:v3`):**
   - Endpoint: `POST https://api.sarvam.ai/text-to-speech`
   - Payload: JSON with `text`, `language_code`, `speaker`, `model: "bulbul:v3"`, `pace: 1.0`.
   - Response: `{"audios": ["<base64_encoded_wav>"]}`.
4. **Limits & Audio Validation:**
   - Audio file size strictly capped at 15 MB.
   - Container format checked using magic bytes (RIFF/WAV, WebM, MP3 ID3/Sync, OGG, M4A ftyp).
   - TTS input bounded to 2500 characters.

### 5.3 Centralized Regional Language Registry
All supported languages are managed centrally in `backend/app/core/languages.py`:
- Supported codes: `hi-IN` (Hindi), `te-IN` (Telugu), `ta-IN` (Tamil), `mr-IN` (Marathi), `kn-IN` (Kannada), `bn-IN` (Bengali), `gu-IN` (Gujarati), `ml-IN` (Malayalam), `pa-IN` (Punjabi), `or-IN` (Odia), `en-IN` (Indian English).
- Both STT and TTS capabilities are mapped per dialect with default regional voice profiles.

### 5.4 Security & Observability
- **Key Hygiene:** Frontend interacts solely with our FastAPI proxy; browser never handles Sarvam keys.
- **Sanitized Logging:** Audio byte streams and authentication headers are masked. Request ID, language, model name, file size, and latency are recorded via structured logging.

---

## 6. Conversational Agricultural RAG Intelligence (Phase 4 Implemented)

### 6.1 10-Layer Conversational Architecture

```
FARMER QUESTION (Text or Transcribed Voice)
       │
       ▼
[Layer 1] Query Preprocessing Service (`query_preprocessor.py`)
       │ Normalization, Unicode NFKC, preservation of regional scripts and IDs
       ▼
[Layer 2] Intent Classification Service (`intent_classifier.py`)
       │ Explicit: CROP_ADVISORY, PEST_DISEASE, MANDI_PRICE, GOVERNMENT_SCHEME,
       │           GENERAL_AGRICULTURE, UNSUPPORTED, UNKNOWN
       ▼
[Layer 3] Agricultural Context Extractor (`context_extractor.py`)
       │ Extracts crops, varieties, states, districts, seasons, pests (NO guessing)
       ▼
[Layer 4] Specialized Retrieval Engine (`retrieval_service.py`)
       │ Specialized by intent:
       │ - CROP / PEST: Vector search (768-dim embeddings) & hybrid keyword overlap
       │ - GOVERNMENT_SCHEME: Structured search over official schemes
       │ - MANDI_PRICE: Structured query over mandi prices (REJECTS development_seed)
       │ - UNSUPPORTED: Returns empty evidence
       ▼
[Layer 5] Pre-LLM Evidence Validation & Abstention Gate (`grounding_validator.py`)
       │ Checks sufficiency and threshold (>= 0.55).
       │ If insufficient -> ABSTAINS IMMEDIATELY (LLM is NOT called).
       ▼
[Layer 6] Grounded Prompt Construction (`advisor_orchestrator.py`)
       │ Strict system instructions: facts from evidence ONLY, zero dosage invention.
       ▼
[Layer 7] LLM Provider Execution (`llm_provider.py`)
       │ Official Gemini Flash (gemini-3.8-flash) or MockLLMProvider for offline tests.
       ▼
[Layer 8] Post-LLM Grounding Safety Heuristic (`grounding_validator.py`)
       │ Verifies output numbers, chemical dosages, prices, and citation validity.
       ▼
[Layer 9] Response Formatter & Citation Attribution
       │ Generates structured AdvisorQueryResponse with provenance & data_origin.
       ▼
[Layer 10] Conversation Persistence
         Logs to `conversations`, `query_logs`, and `response_logs`.
```

### 6.2 Strict Factual Grounding & Abstention Safeguards
- **Zero Hallucination Disclaimer:** The system never claims to be mathematically "hallucination-proof"; it is described as *"evidence-grounded with abstention when sufficient evidence is unavailable."*
- **Source Specialization:** Mandi price questions are NEVER answered from agricultural PDFs or general LLM knowledge.
- **Data Origin Honesty:** `development_seed` records are strictly filtered out and rejected as authoritative evidence.
- **Government Scheme Verification:** Eligibility is never assumed or inferred when required farmer criteria are unverified.


