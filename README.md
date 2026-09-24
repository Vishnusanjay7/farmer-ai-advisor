# KrishiVaani — Farmer AI Advisor

> **Regional Language Voice-Based AI Advisory Assistant for Small and Marginal Farmers Using Authoritative Government Agricultural Data**

[![Backend Tests](https://img.shields.io/badge/Backend%20Tests-140%2F140%20PASS-brightgreen)](#testing)
[![Frontend Build](https://img.shields.io/badge/Frontend%20Build-Passing-brightgreen)](#frontend-setup)
[![Database](https://img.shields.io/badge/Database-PostgreSQL%20%2B%20pgvector-blue)](#database--vector-storage)
[![Architecture](https://img.shields.io/badge/Design-Grounding%20%2B%20Abstention-orange)](#core-principle)

---

## Core Principle

> **"Official agricultural data is the source of truth; AI retrieves, validates, and communicates it."**

Generic Large Language Models (LLMs) pose severe risks to smallholder farmers by hallucinating fertilizer dosages, spray schedules, and scheme qualifications. KrishiVaani eliminates speculative generation by treating official agricultural repositories as the absolute authority:
- The AI model never acts as a primary knowledge base.
- When authoritative evidence is retrieved, the LLM is restricted to evidence-grounded synthesis in the farmer's regional dialect.
- When sufficient evidence is unavailable, the system **explicitly abstains** and redirects the farmer to the official **Kisan Call Center (1800-180-1551)** or local Krishi Vigyan Kendra (KVK).

---

## Problem & Solution

### The Challenge
- **Language & Literacy Barriers:** 86% of Indian farmers are small and marginal, often reliant on oral communication and regional dialects.
- **Fragmented Information:** Crop advisories, market mandi prices, and welfare schemes are scattered across disconnected portals.
- **Risk of LLM Hallucinations:** Inaccurate crop disease advice or fertilizer miscalculations can wipe out a season's income.

### Our Solution
KrishiVaani delivers a multimodal (voice-first & text) advisory assistant that connects directly to verified public agronomic data:
1. **Voice Query in Regional Dialect:** Captured via Sarvam AI Speech-to-Text (`saaras:v3`).
2. **Intent Classification & Extraction:** Context extraction (crop, state, district, growth stage) without external API overhead.
3. **Multi-Path Retrieval:**
   - **Agronomy & Crop Management:** 768-dimensional dense vector embeddings with HNSW cosine similarity in Supabase PostgreSQL (`pgvector`).
   - **Welfare Schemes:** Structured querying against verified Central & State Government schemes.
   - **Market Mandi Prices:** Structured APMC arrival and modal price records.
4. **Evidence Sufficiency Gate:** Threshold check (`similarity >= 0.55`); low-confidence queries bypass the LLM and trigger safe abstention.
5. **Grounded Synthesis:** Gemini 3.8 Flash synthesizes verified facts with mandatory provenance citations.
6. **Voice Response Delivery:** Sarvam AI Text-to-Speech (`bulbul:v3`) delivers natural spoken answers.

---

## Core Features

- 🎙️ **Regional Voice Interface:** Spoken query input and audio response in Hindi and English, architected for multi-language regional expansion.
- 🌾 **Authoritative Crop Guidance:** Evidence-backed package of practices for major crops (wheat, rice, mustard, pulses, etc.) sourced from ICAR and State Agricultural Universities.
- 🏛️ **Government Welfare Scheme Navigation:** Instant guidance on PM-KISAN, PMFBY (Crop Insurance), PM-KMY (Pension), Agriculture Infrastructure Fund (AIF), and Sub-Mission on Agricultural Mechanization (SMAM).
- 📊 **APMC Mandi Price Intelligence:** Real-time and cached daily market arrival and modal prices from Agmarknet (data.gov.in).
- 🛡️ **Safety & Safe Abstention Boundary:** Refuses out-of-domain queries (e.g. sports, politics) and explicitly abstains when authoritative evidence is missing, preventing hallucinated guidance.
- 📜 **Full Provenance & Citations:** Every advisory includes the issuing authority, document source, publication date, and section references.
- 🔒 **Enterprise-Grade Security:** Secret sanitization middleware, instance-local sliding-window rate limiting, and zero credential leakage.

---

## System Architecture

```
                    ┌───────────────────────────────────┐
                    │      Farmer Client (Web / PWA)    │
                    │      Next.js 14 + Web Audio API   │
                    └───────────────┬───────────────────┘
                                    │ Multimodal (Voice/Text)
                                    ▼
                    ┌───────────────────────────────────┐
                    │      FastAPI Backend Gateway      │
                    │      Request Logging & Security   │
                    └───────────────┬───────────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          │                         │                         │
          ▼                         ▼                         ▼
┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│  Voice Pipeline  │      │  Orchestration   │      │   Rate Limiter   │
│  Sarvam AI       │      │  Preprocess &    │      │  Sliding Window  │
│  Saaras v3 (STT) │      │  Intent Engine   │      │  (Instance-Local)│
│  Bulbul v3 (TTS) │      └─────────┬────────┘      └──────────────────┘
└──────────────────┘                │
                                    ▼
                    ┌───────────────────────────────────┐
                    │      Multi-Path Retrieval         │
                    ├───────────────────────────────────┤
                    │ • pgvector Cosine Search (768-dim)│
                    │ • Government Schemes Lookup       │
                    │ • Agmarknet APMC Mandi Data       │
                    └───────────────┬───────────────────┘
                                    │
                        [Evidence Sufficiency Gate]
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
            (Score < 0.55)                  (Score >= 0.55)
                    ▼                               ▼
        ┌───────────────────────┐       ┌───────────────────────┐
        │    Safe Abstention    │       │   Grounded Synthesis  │
        │  Directs to Kisan     │       │   Google Gemini Flash │
        │  Call Center (1800)   │       │   Strict Evidence Only│
        └───────────────────────┘       └───────────┬───────────┘
                                                    │
                                                    ▼
                                        ┌───────────────────────┐
                                        │  Validated Advisory   │
                                        │  with Citations       │
                                        └───────────────────────┘
```

For editable PowerPoint slides, architecture SVGs, and complete ER diagrams, visit [`hackathon-diagrams/`](file:///c:/farmer-ai-advisor/hackathon-diagrams/).

---

## Authoritative Data Sources

| Source | Organization | Content Covered |
| :--- | :--- | :--- |
| **ICAR Package of Practices** | Indian Council of Agricultural Research | Crop sowing, seed rate, irrigation schedules, disease management |
| **State Agricultural Universities (SAUs)** | PAU, IARI, CCS HAU | Regional soil management, fertilizer application, crop varieties |
| **MoAFW Scheme Guidelines** | Ministry of Agriculture & Farmers Welfare | PM-KISAN, PMFBY, PM-KMY, AIF, SMAM eligibility & benefits |
| **Agmarknet Daily Market Data** | Directorate of Marketing & Inspection (DMI) | Real-time APMC mandi commodity arrivals and modal prices |

---

## Technology Stack

- **Backend:** Python 3.11, FastAPI, SQLAlchemy ORM, Pydantic v2, Uvicorn
- **Database & Vectors:** PostgreSQL 15+, pgvector 0.8+, Supabase Managed Cloud
- **Embeddings:** Google `gemini-embedding-001` (768-dimensional dense vector space)
- **Conversational LLM:** Google `gemini-3.8-flash` (with automated bounded fallback)
- **Voice Services:** Sarvam AI REST API (`saaras:v3` STT, `bulbul:v3` TTS)
- **Frontend:** Next.js 14 (App Router), React 18, TypeScript, Vanilla CSS
- **Testing:** Pytest, pytest-asyncio, HTTPX

---

## Project Structure

```
farmer-ai-advisor/
├── backend/
│   ├── app/
│   │   ├── api/v1/            # REST API endpoints (advisor, voice, mandi, schemes, health)
│   │   ├── core/              # Settings, security, logging, language codes, prompts
│   │   ├── db/                # Database session, models, and migrations
│   │   ├── providers/         # LLM, STT, TTS, Mandi, and Embedding provider adapters
│   │   ├── schemas/           # Pydantic request/response schemas
│   │   └── services/          # Orchestrator, retrieval service, and intent extraction
│   ├── .env.example           # Backend environment template
│   └── requirements.txt       # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── app/               # Next.js App Router pages and layout
│   │   ├── components/        # Audio recorder, advisory chat, scheme viewer, mandi cards
│   │   └── lib/               # API client, audio utilities, types
│   ├── .env.example           # Frontend environment template
│   └── package.json           # Frontend dependencies
├── supabase/
│   └── migrations/            # Idempotent PostgreSQL + pgvector schema migrations
├── scripts/                   # Knowledge ingestion, scheme seeding, audit, and E2E verification
├── docs/                      # Architectural specifications, API specs, and readiness guides
├── hackathon-diagrams/        # Presentation-ready diagrams (PPTX, SVG, PNG)
└── tests/                     # 140 automated backend unit and integration tests
```

---

## Environment Configuration

Copy the template to your local environment file:

```bash
cp .env.example .env
```

### Required Configuration Variables

| Variable | Description | Example / Placeholder |
| :--- | :--- | :--- |
| `ENVIRONMENT` | Target environment (`development`, `staging`, `production`) | `development` |
| `BACKEND_HOST` | Bind address | `0.0.0.0` |
| `BACKEND_PORT` | HTTP port | `8000` |
| `ALLOWED_ORIGINS` | Comma-separated CORS allowed web origins | `http://localhost:3000,http://127.0.0.1:3000` |
| `DATABASE_URL` | PostgreSQL connection string with pgvector | `postgresql://postgres:[PASSWORD]@[HOST]:5432/postgres` |
| `GEMINI_API_KEY` | Google AI Studio Gemini API Key | `your_gemini_api_key_here` |
| `LLM_MODEL` | Approved Gemini model identifier | `gemini-3.8-flash` |
| `EMBEDDING_MODEL` | Approved 768-dim embedding model | `gemini-embedding-001` |
| `SARVAM_API_KEY` | Sarvam AI Regional Voice API Key | `your_sarvam_api_key_here` |
| `DATA_GOV_IN_API_KEY` | Data.gov.in Agmarknet API Key | `your_data_gov_in_api_key_here` |
| `NEXT_PUBLIC_BACKEND_URL` | Frontend URL to backend service | `http://localhost:8000` |

> [!WARNING]
> Never commit `.env`, `.env.staging`, or `.env.production` files. Use `.env.example` templates for version control.

---

## Local Development Setup

### Prerequisites
- Python 3.11+
- Node.js 18+ and npm
- PostgreSQL with `pgvector` extension (or local SQLite for offline dev)

### 1. Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create and activate virtual environment
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start local development server
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`. Swagger documentation is accessible at `http://localhost:8000/docs` in development mode.

### 2. Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Start Next.js development server
npm run dev
```

Open `http://localhost:3000` in your browser.

---

## Testing & Quality Assurance

The codebase includes comprehensive test coverage for offline mocks, live provider adapters, grounding gates, rate limiting, and security boundaries.

### Run Backend Tests

```bash
# Execute full backend test suite (140 tests)
python -m pytest tests/ -v
```

### Run Frontend Production Build

```bash
# Verify TypeScript compilation and production bundle
cd frontend
npm run build
```

### Staging Verification Smoke Tests

```bash
# Run comprehensive E2E staging retrieval verification
python scripts/test_staging_e2e_verification.py
```

---

## Safety & Ethics Statement

- **Non-Speculative Agricultural Advice:** Chemical pesticide dosages and restricted chemical advice are constrained strictly to verbatim ICAR recommendations.
- **Fail-Safe Abstention:** When queries fall outside official documents or match low similarity, the model produces no speculative extrapolation.
- **Helpline Escalation:** Farmers are guided to accredited government extension officers via the toll-free Kisan Call Center at **1800-180-1551**.
