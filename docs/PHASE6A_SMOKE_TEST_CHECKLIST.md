# Phase 6A — Production Smoke Test Checklist

**Operator Guide**: Regional Language Voice-Based AI Advisory Assistant  
**Target Environment**: Staging / Production Deployment (Vercel + Render/Railway + Supabase)

---

## 1. Pre-Deployment Verification Checklist

Before running production smoke tests, verify that all cloud services and credentials are active:

- [ ] **Supabase PostgreSQL**: Instance is active; extensions `uuid-ossp`, `pgcrypto`, `vector` enabled.
- [ ] **Database Schema**: Migrations `20260922000000` and `20260922000001` executed successfully.
- [ ] **Seed Records**: 5 government schemes and 26 knowledge chunks verified in database.
- [ ] **Backend Service**: Deployed on Render/Railway; `DATABASE_URL`, `SARVAM_API_KEY`, `GEMINI_API_KEY`, `DATA_GOV_IN_API_KEY` configured in environment settings.
- [ ] **Frontend Application**: Deployed on Vercel; `NEXT_PUBLIC_BACKEND_URL` configured to point to backend service.
- [ ] **HTTPS Enforced**: Both frontend and backend URLs use valid HTTPS certificates (required for microphone access).
- [ ] **CORS Configured**: Backend `ALLOWED_ORIGINS` includes the frontend Vercel domain.

---

## 2. Production Smoke Test Suite

Execute the following 13 smoke tests in sequence:

### ST-01: Backend Health Check
- **Method**: `GET https://<BACKEND_HOST>/api/v1/health`
- **Expected Response**: HTTP 200 `{"status": "ok", "service": "farmer-ai-backend", "version": "0.1.0"}`
- **Pass Criteria**: Status code 200, response time < 500ms.
- [ ] PASS / FAIL

---

### ST-02: Frontend UI Availability
- **Action**: Navigate to `https://<FRONTEND_HOST>` in browser.
- **Expected UI**:
  - Outlined banner / title: "Regional Language Voice-Based AI Advisory Assistant"
  - Language selector dropdown with 11 regional Indian languages
  - Large microphone button with idle visual indicator
  - Local farmer context drawer (State, District, Crops)
  - Text input toggle button
- **Pass Criteria**: Page renders in < 2s without JavaScript console errors.
- [ ] PASS / FAIL

---

### ST-03: Language Registry Verification
- **Method**: `GET https://<BACKEND_HOST>/api/v1/voice/languages`
- **Expected Response**: HTTP 200 with list of 11 supported languages (`hi-IN`, `te-IN`, `ta-IN`, `mr-IN`, `kn-IN`, `en-IN`, etc.).
- **Pass Criteria**: Contains `hi-IN` (Hindi) and `te-IN` (Telugu) with active STT and TTS capabilities.
- [ ] PASS / FAIL

---

### ST-04: Grounded Agricultural Advisory (Text Flow)
- **Method**: `POST https://<BACKEND_HOST>/api/v1/advisor/query`
- **Payload**:
  ```json
  {
    "query_text": "What irrigation schedule should be followed for Wheat?",
    "input_channel": "text",
    "farmer_context": {"language": "en-IN", "crop": "Wheat"}
  }
  ```
- **Expected Response**:
  - `intent`: `"CROP_ADVISORY"`
  - `is_grounded`: `true`
  - `abstained`: `false`
  - Wheat context recognized
  - Sufficient authoritative evidence retrieved
  - Grounded response detailing critical irrigation stages (e.g., Crown Root Initiation / CRI stage at 20–25 days after sowing)
  - Citation to authoritative ICAR / SAU Wheat Package of Practices
  - No invented fertilizer dosage
  - No unsupported chemical recommendation
- **Pass Criteria**: Grounded answer returned with verifiable citation and similarity score >= 0.55.
- [ ] PASS / FAIL


---

### ST-05: Multi-Turn Conversation Continuity
- **Method**: `POST https://<BACKEND_HOST>/api/v1/advisor/query` (Turn 2 on same `conversation_id`)
- **Payload**:
  ```json
  {
    "conversation_id": "<ID_FROM_ST_04>",
    "query_text": "How do I prevent yellow rust?",
    "input_channel": "text",
    "farmer_context": {"language": "en-IN"}
  }
  ```
- **Expected Response**:
  - Second turn correctly inherits `crop: "Wheat"` from previous turn.
  - Recommends Propiconazole 25% EC (Tilt) and resistant varieties (HD 3086, PBW 550).
  - Does NOT ask the farmer "which crop are you referring to?".
- **Pass Criteria**: Entity inheritance verified; grounded advice provided.
- [ ] PASS / FAIL

---

### ST-06: Deterministic Mandi Price Query
- **Method**: `POST https://<BACKEND_HOST>/api/v1/advisor/query`
- **Payload**:
  ```json
  {
    "query_text": "What is the wheat price in Indore mandi?",
    "input_channel": "text",
    "farmer_context": {"language": "en-IN", "state": "Madhya Pradesh"}
  }
  ```
- **Expected Response**:
  - `intent`: `"MANDI_PRICE"`
  - `llm_called`: `false` (Deterministic Agmarknet extraction)
  - Min price, max price, modal price, arrival date, and market name clearly formatted.
  - `data_origin`: `"production_live"` or `"production_cached"`.
- **Pass Criteria**: Exact numeric prices formatted without LLM synthesis; arrival date explicitly stated.
- [ ] PASS / FAIL

---

### ST-07: Government Scheme Criteria Retrieval
- **Method**: `POST https://<BACKEND_HOST>/api/v1/advisor/query`
- **Payload**:
  ```json
  {
    "query_text": "Who is eligible for PM-KISAN scheme and what documents are required?",
    "input_channel": "text",
    "farmer_context": {"language": "en-IN"}
  }
  ```
- **Expected Response**:
  - `intent`: `"GOVERNMENT_SCHEME"`
  - `llm_called`: `false`
  - Lists ₹6,000/year benefit in 3 installments.
  - Documented eligibility criteria: landholding farmer families, exclusions for institutional/tax-payers.
  - Required documents: Aadhaar, Land records (Khata/Patta), Bank account.
  - Official URL: `https://pmkisan.gov.in`.
  - Disclaims individual farmer eligibility: *"Documented scheme eligibility criteria (verify at official portal)"*.
- **Pass Criteria**: Structured scheme criteria retrieved without claiming individual eligibility.
- [ ] PASS / FAIL

---

### ST-08: Safe Abstention on Insufficient Evidence
- **Method**: `POST https://<BACKEND_HOST>/api/v1/advisor/query`
- **Payload**:
  ```json
  {
    "query_text": "What is the drone spraying schedule for dragon fruit in Ladakh?",
    "input_channel": "text",
    "farmer_context": {"language": "en-IN"}
  }
  ```
- **Expected Response**:
  - `is_grounded`: `false`
  - `abstained`: `true`
  - `confidence_score` < 0.55
  - Transparent abstention message: *"I do not have verified agricultural data for dragon fruit cultivation in Ladakh from official ICAR or State Agriculture University packages of practices."*
- **Pass Criteria**: System abstains cleanly; zero hallucinated facts or schedules.
- [ ] PASS / FAIL

---

### ST-09: Safe Abstention on Out-of-Scope Query
- **Method**: `POST https://<BACKEND_HOST>/api/v1/advisor/query`
- **Payload**:
  ```json
  {
    "query_text": "Who won the cricket match yesterday?",
    "input_channel": "text",
    "farmer_context": {"language": "en-IN"}
  }
  ```
- **Expected Response**:
  - `intent`: `"UNSUPPORTED"`
  - `llm_called`: `false`
  - `abstained`: `true`
  - Message: *"I am an agricultural advisory assistant dedicated to farming queries..."*
- **Pass Criteria**: Non-agricultural query rejected immediately without calling LLM.
- [ ] PASS / FAIL

---

### ST-10: Sarvam Speech-to-Text (STT) Live Verification
- **Method**: `POST https://<BACKEND_HOST>/api/v1/voice/stt`
- **Form Data**: `audio_file=@test_audio_hindi.wav`, `language="hi-IN"`
- **Expected Response**: HTTP 200 with accurate Hindi transcript, detected language `"hi-IN"`, confidence > 0.85.
- **Pass Criteria**: Successful transcription within 5 seconds.
- [ ] PASS / FAIL

---

### ST-11: Sarvam Text-to-Speech (TTS) Live Verification
- **Method**: `POST https://<BACKEND_HOST>/api/v1/voice/tts`
- **Payload**:
  ```json
  {
    "text": "गेहूं में पहली सिंचाई बुवाई के 20 से 25 दिन बाद सीआरआई अवस्था में करें।",
    "language": "hi-IN",
    "speaker": "shubh"
  }
  ```
- **Expected Response**: HTTP 200 with `audio_base64` string and `audio_format: "wav"`.
- **Pass Criteria**: Valid Base64 audio payload generated; plays clearly in browser.
- [ ] PASS / FAIL

---

### ST-12: Complete End-to-End Voice Round Trip
- **Action in Frontend UI**:
  1. Select Hindi (`hi-IN`).
  2. Click Microphone button.
  3. Speak: *"गेहूं में सिंचाई कब करनी चाहिए?"*
  4. Click Stop recording.
- **Expected UI State Transitions**:
  `IDLE` -> `RECORDING` -> `UPLOADING` -> `TRANSCRIBING` -> `READY_TO_ASK` -> `THINKING` -> `ANSWER_READY` -> `SPEAKING`.
- **Pass Criteria**: Transcript visible, grounded answer displayed with PAU/ICAR citation, and audio plays automatically.
- [ ] PASS / FAIL

---

### ST-13: Fail-Safe Resilience Test (TTS Outage Simulation)
- **Action**: Simulate TTS failure (e.g. invalid speaker or temporary upstream error).
- **Expected UI Behavior**:
  - Frontend transitions safely to `ANSWER_READY` (NOT `ERROR`).
  - Text answer, advice bullets, and official citations remain fully visible.
  - A subtle notification states: "Audio playback unavailable; text advice is fully accessible."
- **Pass Criteria**: Text response and citations are never destroyed upon TTS failure.
- [ ] PASS / FAIL

---

## 3. Post-Test Signoff

| Role | Signoff Name | Date / Time | Verdict |
| :--- | :--- | :--- | :--- |
| **Lead Operator** | | | [ ] APPROVED / [ ] BLOCKED |
| **Technical Evaluator** | | | [ ] APPROVED / [ ] BLOCKED |
