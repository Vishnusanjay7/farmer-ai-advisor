# REST API Specification (FastAPI)

> **Phase 5 Status**: 11 functional REST endpoints active and verified via automated test suite.
> - **Active Endpoints**: `GET /api/v1/health`, `GET /`, `GET /api/v1/mandi/prices`, `GET /api/v1/schemes/search`, `GET /api/v1/agriculture/sources`, `GET /api/v1/agriculture/topics`, `POST /api/v1/voice/stt`, `POST /api/v1/voice/tts`, `GET /api/v1/voice/languages`, `POST /api/v1/advisor/query`, `GET /api/v1/conversations/{conversation_id}`.

---

## 1. Implemented Endpoints

### 1.1 `GET /api/v1/health`
Operational status check.

**Response:** `200 OK`
```json
{
  "status": "ok",
  "service": "farmer-ai-backend",
  "version": "0.1.0"
}
```

---

### 1.2 `GET /api/v1/mandi/prices`
Retrieves market commodity prices from Data.gov.in Agmarknet API, falling back to local PostgreSQL cache.

**Query Parameters:**
- `state` (string, required): e.g. `Madhya Pradesh`
- `district` (string, optional): e.g. `Indore`
- `commodity` (string, optional): e.g. `Wheat`
- `page` (int, default 1): Page number
- `page_size` (int, default 20): Records per page

**Response:** `200 OK`
```json
{
  "total": 1,
  "page": 1,
  "page_size": 20,
  "query_state": "Madhya Pradesh",
  "query_district": "Indore",
  "query_commodity": "Wheat",
  "records": [
    {
      "state": "Madhya Pradesh",
      "district": "Indore",
      "market": "Indore",
      "commodity": "Wheat",
      "variety": "Lokwan",
      "grade": "FAQ",
      "arrival_date": "2026-09-22",
      "min_price": 2450.0,
      "max_price": 2850.0,
      "modal_price": 2650.0,
      "source": "Agmarknet",
      "data_origin": "production_live",
      "fetched_at": "2026-09-22T20:30:00Z"
    }
  ]
}
```

---

### 1.3 `GET /api/v1/schemes/search`
Searches authoritative central and state agricultural schemes.

**Query Parameters:**
- `q` (string, optional): Search keyword (e.g. `insurance`, `credit`, `soil`, `kisan`)
- `state` (string, optional): Filter by state or `Central`
- `page` (int, default 1): Page number
- `page_size` (int, default 10): Items per page

**Response:** `200 OK`
```json
{
  "total": 1,
  "page": 1,
  "page_size": 10,
  "schemes": [
    {
      "id": "c1f7a4e0-...",
      "scheme_code": "PMFBY",
      "scheme_name": "Pradhan Mantri Fasal Bima Yojana (PMFBY)",
      "name_translations": { "hi": "प्रधानमंत्री फसल बीमा योजना" },
      "short_description": "Comprehensive risk insurance service for farmers against natural calamities...",
      "benefits_summary": "Maximum premium: 2% for Kharif, 1.5% for Rabi crops...",
      "eligibility_criteria": ["All farmers growing notified crops in notified areas..."],
      "required_documents": ["Aadhaar Card", "Bank Passbook", "Land possession certificate"],
      "application_process": "Enrollment through National Crop Insurance Portal (pmfby.gov.in)...",
      "official_portal_url": "https://pmfby.gov.in",
      "sponsoring_agency": "Ministry of Agriculture & Farmers Welfare",
      "state_scope": "Central",
      "last_verified_date": "2026-08-01",
      "is_active": true
    }
  ]
}
```

---

### 1.4 `GET /api/v1/agriculture/sources`
Returns verified authoritative source documents with full provenance and indexed chunk counts.

**Query Parameters:**
- `source_type` (string, optional): e.g. `ICAR`, `SAU_POP`, `KVK`
- `state` (string, optional): e.g. `Telangana`, `Punjab`
- `page` (int, default 1)
- `page_size` (int, default 20)

**Response:** `200 OK`
```json
{
  "total": 6,
  "page": 1,
  "page_size": 20,
  "sources": [
    {
      "id": "02920f7e-...",
      "title": "Integrated Pest & Disease Management for Rice (Paddy) in India",
      "source_name": "ICAR-IIRR Rice Integrated Pest Management 2024",
      "source_type": "ICAR",
      "issuing_authority": "ICAR - Indian Institute of Rice Research (IIRR), Hyderabad",
      "state_applicability": "All-India",
      "official_document_url": "https://icar-iirr.org/advisory/pop_rice_ipm_2024.pdf",
      "publication_year": 2024,
      "verified_by_expert": true,
      "source_date": "2024-06-15",
      "language": "en",
      "total_chunks": 5
    }
  ]
}
```

---

### 1.5 `GET /api/v1/agriculture/topics`
Returns available agronomic topics and chunk distributions in the knowledge store.

**Query Parameters:**
- `crop` (string, optional): Filter by crop name

**Response:** `200 OK`
```json
{
  "total_topics": 6,
  "topics": [
    {
      "topic": "Integrated Pest Management",
      "crop_name": "Paddy",
      "chunk_count": 5
    },
    {
      "topic": "Production Technology",
      "crop_name": "Wheat",
      "chunk_count": 4
    }
  ]
}
```

---

### 1.6 `POST /api/v1/voice/stt`
Transcribes regional spoken audio using Sarvam AI (`saaras:v3`).

**Content-Type:** `multipart/form-data`

**Form Parameters:**
- `file` (UploadFile, required): Audio file (WAV, WebM, MP3, OGG, M4A), max size 15 MB.
- `language_code` (string, optional): Regional language code (e.g., `hi-IN`, `te-IN`, `ta-IN`).

**Response:** `200 OK`
```json
{
  "transcript": "गेहूं में यूरिया कब डालना चाहिए?",
  "language_code": "hi-IN",
  "confidence": 0.95,
  "model_used": "saaras:v3",
  "duration_seconds": 3.4
}
```

**Errors:**
- `400 Bad Request`: Empty file, invalid magic byte container, or file exceeds 15 MB.
- `422 Unprocessable Entity`: Unsupported language code.
- `502 Bad Gateway`: Downstream provider error or timeout.
- `503 Service Unavailable`: Missing provider credentials.

---

### 1.7 `POST /api/v1/voice/tts`
Synthesizes regional speech from text using Sarvam AI (`bulbul:v3`).

**Content-Type:** `application/json`

**Request Body:**
```json
{
  "text": "गेहूं में पहली सिंचाई के समय यूरिया का प्रयोग करें।",
  "language": "hi-IN",
  "speaker": "shubh",
  "pace": 1.0
}
```

**Response:** `200 OK`
```json
{
  "audio_base64": "UklGRi...",
  "format": "wav",
  "language": "hi-IN",
  "speaker": "shubh",
  "model_used": "bulbul:v3"
}
```

**Errors:**
- `400 Bad Request`: Empty text, or text exceeds 2500 characters.
- `422 Unprocessable Entity`: Unsupported language code.
- `502 Bad Gateway`: Downstream provider error or timeout.
- `503 Service Unavailable`: Missing provider credentials.

---

### 1.8 `GET /api/v1/voice/languages`
Lists all supported regional Indian languages and their STT/TTS capabilities.

**Response:** `200 OK`
```json
{
  "total": 11,
  "languages": [
    {
      "code": "hi-IN",
      "name": "Hindi",
      "native_name": "हिन्दी",
      "stt_supported": true,
      "tts_supported": true,
      "stt_model": "saaras:v3",
      "tts_model": "bulbul:v3",
      "default_speaker": "shubh"
    }
  ]
}
```

---

### 1.9 `POST /api/v1/advisor/query`
Conversational agricultural advisory query through the 10-layer grounded RAG pipeline.

**Content-Type:** `application/json`

**Request Body:**
```json
{
  "query": "How do I control yellow stem borer in paddy?",
  "language": "en-IN",
  "farmer_context": {
    "crop": "Paddy",
    "state": "Tamil Nadu"
  },
  "conversation_id": "optional-uuid"
}
```

**Response:** `200 OK`
```json
{
  "query_id": "c76f68c2-...",
  "conversation_id": "b18b4e7a-...",
  "original_query": "How do I control yellow stem borer in paddy?",
  "normalized_query": "How do I control yellow stem borer in paddy?",
  "language": "en-IN",
  "intent": "PEST_DISEASE",
  "extracted_context": {
    "crop": "Paddy",
    "pest_disease": "Yellow stem borer",
    "state": "Tamil Nadu"
  },
  "response_text": "According to ICAR - Indian Institute of Rice Research: Yellow Stem Borer causes dead hearts and white ears. Install sex pheromone traps at 4-5 traps per acre for monitoring...",
  "evidence": [
    {
      "evidence_id": "chunk_02920f7e-...",
      "title": "Integrated Pest & Disease Management for Rice (Paddy) in India",
      "issuing_authority": "ICAR - Indian Institute of Rice Research (IIRR), Hyderabad",
      "official_url": "https://icar-iirr.org/advisory/pop_rice.pdf",
      "relevance_score": 0.85,
      "status": "authoritative",
      "data_origin": "production_cached"
    }
  ],
  "citations": [
    {
      "title": "Integrated Pest & Disease Management for Rice (Paddy) in India",
      "issuing_authority": "ICAR - Indian Institute of Rice Research (IIRR), Hyderabad",
      "official_url": "https://icar-iirr.org/advisory/pop_rice.pdf",
      "relevance_score": 0.85,
      "data_origin": "production_cached"
    }
  ],
  "is_grounded": true,
  "abstained": false,
  "abstention_reason": null,
  "data_origin": "production_cached",
  "llm_called": true
}
```

**Abstention Response Example (When Evidence is Insufficient or Out-of-Domain):**
```json
{
  "query_id": "8fa21e4a-...",
  "intent": "UNSUPPORTED",
  "response_text": "I couldn't find enough verified agricultural information in official ICAR, SAU, or government sources to answer that safely. (Query is outside the supported agricultural advisory scope.)",
  "is_grounded": false,
  "abstained": true,
  "abstention_reason": "Query is outside the supported agricultural advisory scope.",
  "llm_called": false
}
```

---

### 1.11 `GET /api/v1/conversations/{conversation_id}`
Retrieves chronologically ordered interaction turns for a conversation thread.

**Path Parameters:**
- `conversation_id` (string, required): Unique conversation UUID

**Response:** `200 OK`
```json
{
  "conversation_id": "9f113193-0573-46b8-8f81-4261c62da925",
  "title": "Advisory Query: गेहूं में सिंचाई कब करनी चाहिए?",
  "total_turns": 2,
  "turns": [
    {
      "query_id": "turn-1-uuid",
      "conversation_id": "9f113193-...",
      "input_channel": "voice",
      "detected_language": "hi-IN",
      "query_text": "गेहूं में सिंचाई कब करनी चाहिए?",
      "classified_intent": "CROP_ADVISORY",
      "extracted_entities": { "crop": "Wheat" },
      "response_text": "Critical Irrigation Stages: 1. Crown Root Initiation (CRI) stage...",
      "is_grounded": true,
      "disclaimer_applied": false,
      "citations": [],
      "created_at": "2026-09-22T22:27:55"
    }
  ]
}
```


