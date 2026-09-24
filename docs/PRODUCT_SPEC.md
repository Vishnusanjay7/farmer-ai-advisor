# Product Specification: Regional Language Voice-Based AI Advisory Assistant for Small and Marginal Farmers

## 1. Executive Summary & Problem Statement
Over 86% of Indian farmers are small and marginal (operating on less than 2 hectares). They face critical challenges in accessing timely, authentic, and regional-language agronomic expertise, government welfare schemes, and fair market commodity pricing. Existing digital agricultural portals are largely text-heavy, English/Hindi-centric, fragmented across various state/central silos, and difficult for semi-literate farmers to navigate on mobile devices.

The **Regional Language Voice-Based AI Advisory Assistant** solves this by providing an end-to-end voice-first conversational advisory pipeline directly in the farmer's native dialect. The system retrieves official government data (Agmarknet/data.gov.in, ICAR, KVK, State Agricultural Universities, myScheme), grounds every AI recommendation strictly on verified facts with source attribution, and speaks back to the farmer in clear regional-language speech.

---

## 2. Core Principles & Safety Guardrails
1. **Never Treat AI as the Source of Truth:**
   - LLMs generate language; authoritative government databases provide facts.
   - Every answer MUST be grounded in verified context retrieved beforehand.
2. **Strict Hallucination Prevention on Chemicals & Finances:**
   - Under no circumstances will the system invent pesticide dosages, chemical formulations, government subsidies, or fake mandi prices.
   - If an official recommendation or live price is unavailable, the assistant must transparently say: *"I could not find verified government records for this query. Please consult your local Krishi Vigyan Kendra (KVK) or agriculture officer."*
3. **Source Attribution & Freshness Transparency:**
   - All responses state the data source (e.g., *ICAR Package of Practices 2024*, *Agmarknet Daily Arrival Report*, *myScheme Portal*).
   - Market prices must state the exact reporting date, market yard, and district; never claim historical prices as "today's price".
4. **Resilience & Graceful Degradation:**
   - Network failure or third-party API downtime must degrade gracefully (fallback to cached verified records, clearly marked as "Cached on [date]").

---

## 3. Supported Core Capabilities (MVP Scope)
The MVP strictly implements the 8 mandated capabilities:

1. **Regional-Language Voice Interaction:**
   - Audio input recorded directly from mobile browser/app.
   - Automated speech-to-text (STT) via Sarvam AI (supporting Hindi, Telugu, Tamil, Marathi, Kannada, etc.).
   - Fallback Web Speech API / text input for devices with low network bandwidth.
2. **Crop Advisory:**
   - Sowing windows, seed treatment, irrigation schedules, fertilizer doses based on ICAR and State Agricultural University Package of Practices (PoP).
3. **Pest and Disease Advisory:**
   - Symptom identification from farmer descriptions, prevention strategies, biological and chemical controls grounded in official CIBRC (Central Insecticides Board & Registration Committee) and ICAR advisories.
4. **Government Agricultural Scheme Discovery:**
   - Identification of relevant central and state schemes (e.g., PM-KISAN, PMFBY, KCC, Soil Health Card, PMKSY, Sub-Mission on Agricultural Mechanization).
   - Clear details on benefits, eligibility criteria, required documents, application process, and official links.
5. **Mandi / Market Price Information:**
   - Real-time / recent daily mandi prices from Agmarknet / data.gov.in.
   - District, market, commodity, variety, min price, max price, and modal price (₹/Quintal) with date stamp.
6. **Official-Data-Grounded AI Responses:**
   - Two-tier guardrail system: query router determines domain -> retrieves official records -> validates sufficiency -> grounded LLM synthesis.
7. **Farmer Context & Personalization:**
   - Persistent profile capturing farmer's state, district, landholding size, primary crops, soil type, and preferred dialect.
   - Context automatically injected into queries without requiring the farmer to repeat their location or crops every time.
8. **Regional-Language Text-to-Speech (TTS):**
   - Natural, human-like voice synthesis in the farmer's selected language using Sarvam AI Bulbul model with customizable speech rates and audio playback controls.

---

## 4. Out-of-Scope for MVP (Phase 2 Roadmap)
To ensure strict delivery of a robust, dependable application, the following are explicitly deferred:
- Image-based crop disease computer vision models.
- Real-time hyper-local automated IoT weather alerts.
- Live human video/audio escalation to agronomists.
- Complex multi-season financial predictive modeling.

---

## 5. End-to-End User Flow
```
+-----------------------------------------------------------------------------------+
| 1. Farmer presses large Mic button & speaks in regional language (e.g., Telugu)    |
+-----------------------------------------------------------------------------------+
                                         │
                                         ▼
+-----------------------------------------------------------------------------------+
| 2. Audio streamed to Backend -> Sarvam STT (Saaras model)                         |
|    Output: Native language transcript + detected language code                   |
+-----------------------------------------------------------------------------------+
                                         │
                                         ▼
+-----------------------------------------------------------------------------------+
| 3. Language / Intent / Entity Extractor:                                          |
|    - Intent: [CROP_ADVISORY | PEST_DISEASE | GOVERNMENT_SCHEME | MANDI_PRICE | ...] |
|    - Entities: Crop (Paddy), Pest (Stem Borer), Location (Warangal, Telangana)   |
+-----------------------------------------------------------------------------------+
                                         │
                                         ▼
+-----------------------------------------------------------------------------------+
| 4. Farmer Context Enrichment:                                                     |
|    - Inject profile data (e.g., District: Warangal, Land: 2 Acres, Soil: Red)    |
+-----------------------------------------------------------------------------------+
                                         │
                                         ▼
+-----------------------------------------------------------------------------------+
| 5. Domain Knowledge Router:                                                       |
|    ├─> MANDI_PRICE      : Agmarknet API / Supabase mandi_prices cache             |
|    ├─> GOVERNMENT_SCHEME: Scheme Knowledge Store (myScheme / Gov documents)     |
|    └─> CROP / PEST RAG  : pgvector semantic retrieval over ICAR / SAU documents  |
+-----------------------------------------------------------------------------------+
                                         │
                                         ▼
+-----------------------------------------------------------------------------------+
| 6. Source Validation & Sufficiency Gatekeeper:                                    |
|    - Are relevant sources found above similarity/freshness threshold?             |
|    - If NO -> Return verified refusal disclaimer & KVK contact info.              |
|    - If YES -> Proceed to Grounded Generation.                                    |
+-----------------------------------------------------------------------------------+
                                         │
                                         ▼
+-----------------------------------------------------------------------------------+
| 7. Grounded LLM Response Generation:                                              |
|    - Strict system prompt constraining answer ONLY to verified context            |
|    - Native language generation with citation footnotes                           |
+-----------------------------------------------------------------------------------+
                                         │
                                         ▼
+-----------------------------------------------------------------------------------+
| 8. Regional-Language Text-to-Speech:                                              |
|    - Sarvam TTS (Bulbul model) synthesizes native regional audio stream           |
+-----------------------------------------------------------------------------------+
                                         │
                                         ▼
+-----------------------------------------------------------------------------------+
| 9. Frontend Mobile UI:                                                            |
|    - Shows native transcript, audio playback widget with wave animation           |
|    - Displays verified structured cards (Price card / Scheme card / Advisory card)|
|    - Shows exact source attribution badge and verification date                   |
+-----------------------------------------------------------------------------------+
```

---

## 6. Target User Personas
1. **Ramesh (Marginal Farmer, Uttar Pradesh):**
   - 1.5 acres of wheat and mustard. Semi-literate, speaks Hindi (Bhojpuri-influenced).
   - Needs voice assistance to find nearest mandi prices so local traders don't underpay him.
2. **Lakshmi (Smallholder, Andhra Pradesh):**
   - 2.5 acres of chili and cotton. Speaks Telugu.
   - Notices leaf curling and spots on chili crops; asks in Telugu about biological and safe management practices without getting misdirected by local pesticide retailers pushing unverified chemicals.
3. **Balwinder (Tenant Farmer, Punjab):**
   - Wants to know which crop insurance or mechanization subsidy he is eligible for under state and central schemes and what documents are required.

---

## 7. Success Criteria & KPIs
- **Response Grounding Accuracy:** 100% of factual claims backed by official documents; zero hallucinated pesticide names or dosages.
- **Voice Pipeline Latency:** End-to-end voice-to-voice turn completed in under 3.5 seconds on 4G mobile connections.
- **Speech Recognition Accuracy:** Native Indian regional language STT Word Error Rate (WER) < 12% on agricultural vocabulary.
- **Reliability:** 99.9% uptime with offline seed caches ensuring zero blank screens even during government portal outages.
