# Phase 6A — Production Environment Reference

This document provides the reference guide for all environment variables used across the **Farmer AI Advisory Assistant** platform.

> [!CAUTION]
> **Zero Secret Leakage Rule**: Real API keys, database passwords, and cryptographic secrets must NEVER be committed to Git or exposed to client-side code. This reference illustrates variable formats and schemas only.

---

## 1. Environment Architecture Overview

The system architecture partitions variables into two tiers:
1. **Server-Side Environment Variables (Render / Railway / Supabase)**:
   - Secret API keys, database credentials, server port bindings, and upstream endpoints.
   - Accessible only by Python FastAPI backend runtime.
2. **Client-Side Environment Variables (Vercel)**:
   - Only variables prefixed with `NEXT_PUBLIC_` are accessible in the browser.
   - Contains ONLY the public API endpoint of the backend. Zero secrets permitted.

---

## 2. Server-Side Environment Variables (Backend)

These variables are defined in the backend hosting dashboard (e.g. Render Web Service Environment or Railway Variables).

### 2.1 Core Application & Runtime Settings

| Variable Name | Type | Default | Production Value | Description |
| :--- | :---: | :---: | :---: | :--- |
| `ENVIRONMENT` | string | `development` | `production` | Declares runtime mode. Enables security assertions in production. |
| `LOG_LEVEL` | string | `INFO` | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `DEBUG` | boolean | `true` | `false` | When `false`, disables Swagger `/docs` and hides unhandled exception traces. |
| `BACKEND_HOST` | string | `0.0.0.0` | `0.0.0.0` | Network interface binding inside container/PaaS. |
| `BACKEND_PORT` | integer | `8000` | Dynamic (`$PORT`) | Injected by hosting provider (Render/Railway). |
| `ALLOWED_ORIGINS` | string (CSV) | `http://localhost:3000` | `https://farmer-ai-advisor.vercel.app` | Comma-separated list of CORS origins allowed to access the API. |

---

### 2.2 Database & Vector Storage (Supabase / PostgreSQL)

| Variable Name | Type | Secret? | Format / Example | Description |
| :--- | :---: | :---: | :---: | :--- |
| `DATABASE_URL` | string | **YES** | `postgresql://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:5432/postgres` | Supabase PostgreSQL connection URI. Use Session Pooler port 5432 for synchronous SQLAlchemy backend. |
| `SUPABASE_URL` | string | No | `https://[project-ref].supabase.co` | Optional base URL for Supabase management and client libraries. |
| `SUPABASE_ANON_KEY` | string | Semi | `eyJhbGciOi...` | Supabase public anonymous API key (optional for backend). |
| `SUPABASE_SERVICE_ROLE_KEY` | string | **YES** | `eyJhbGciOi...` | Supabase administrative service role key (optional for backend). |

---

### 2.3 Regional Voice Services (Sarvam AI)

| Variable Name | Type | Secret? | Format / Example | Description |
| :--- | :---: | :---: | :---: | :--- |
| `SARVAM_API_KEY` | string | **YES** | `sk_live_...` or hex token | Subscription key for Sarvam AI Saaras STT and Bulbul TTS. |
| `SARVAM_STT_ENDPOINT` | string | No | `https://api.sarvam.ai/speech-to-text` | Official REST endpoint for regional Speech-to-Text. |
| `SARVAM_TTS_ENDPOINT` | string | No | `https://api.sarvam.ai/text-to-speech` | Official REST endpoint for regional Text-to-Speech. |
| `SARVAM_DEFAULT_SPEAKER` | string | No | `shubh` | Default voice persona (`shubh`, `arvind`, `ratan`, `aditi`). |
| `SARVAM_DEFAULT_LANGUAGE` | string | No | `hi-IN` | Default fallback BCP-47 language tag. |

---

### 2.4 Grounded LLM & Vector Embeddings (Google Gemini)

| Variable Name | Type | Secret? | Format / Example | Description |
| :--- | :---: | :---: | :---: | :--- |
| `GEMINI_API_KEY` | string | **YES** | `AIzaSy...` | Google AI Studio Gemini API key. |
| `LLM_PROVIDER` | string | No | `gemini` | Primary grounded synthesis engine. |
| `LLM_MODEL` | string | No | `gemini-3.8-flash` | Approved Gemini Flash model name. |
| `EMBEDDING_PROVIDER` | string | No | `gemini` | Provider used for 768-dimensional text embeddings. |
| `EMBEDDING_MODEL` | string | No | `gemini-embedding-001` | Approved Gemini embedding model producing 768-dimensional vectors. |
| `EMBEDDING_DIMENSION` | integer | No | `768` | Vector dimension matching PostgreSQL `vector(768)` column. |
| `RAG_TOP_K` | integer | No | `4` | Number of authoritative chunks retrieved per query. |
| `RAG_SIMILARITY_THRESHOLD` | float | No | `0.55` | Pre-LLM relevance gate; values below this trigger abstention. |

---

### 2.5 Government Agricultural Data APIs

| Variable Name | Type | Secret? | Format / Example | Description |
| :--- | :---: | :---: | :---: | :--- |
| `DATA_GOV_IN_API_KEY` | string | **YES** | `579b464db66ec23bdd000001...` | API key from Open Government Data (OGD) Platform India (`data.gov.in`). |
| `AGMARKNET_RESOURCE_ID` | string | No | `9ef84268-d588-465a-a308-a864a43d0070` | Daily Mandi Market Prices resource UUID on data.gov.in. |
| `AGMARKNET_CACHE_TTL_SECONDS` | integer | No | `21600` | Mandi price cache lifespan (21,600 seconds = 6 hours). |

---

### 2.6 Resilience & Operational Safeguards

| Variable Name | Type | Default | Description |
| :--- | :---: | :---: | :--- |
| `ENABLE_MOCK_FALLBACK` | boolean | `true` | If true, gracefully returns cached/verified offline seeds when external API keys are omitted or temporarily unavailable. |
| `MAX_AUDIO_UPLOAD_SIZE_MB` | integer | `15` | Maximum permissible size for uploaded audio files. |
| `RATE_LIMIT_ENABLED` | boolean | `true` | Enables instance-local sliding window rate limiting. |
| `TRUST_PROXY_HEADERS` | boolean | `false` | Safe default. When false, ignores X-Forwarded-For to prevent IP spoofing. Enable only after reverse proxy trust is verified. |

---

## 3. Client-Side Environment Variables (Frontend / Vercel)

These variables are defined in the Vercel Project Settings -> Environment Variables.

| Variable Name | Type | Secret? | Target Environment | Description |
| :--- | :---: | :---: | :---: | :--- |
| `NEXT_PUBLIC_BACKEND_URL` | string (URL) | **NO (Public)** | Production, Preview, Development | Base URL of the deployed FastAPI backend service. Example: `https://farmer-ai-advisor-backend.onrender.com`. In local dev, defaults to `http://localhost:8000`. |

> [!IMPORTANT]
> Do NOT set `GEMINI_API_KEY`, `SARVAM_API_KEY`, or `DATABASE_URL` in Vercel. The Next.js frontend interacts strictly with our backend API proxy, never directly with third-party AI or database endpoints.

---

## 4. Verification & Audit Script

To verify that environment variables are loaded securely without printing their secret values, operators can run:

```bash
# Verify backend configuration loading without leaking values
python -c "from backend.app.core.config import settings; print('Environment:', settings.ENVIRONMENT, '| Gemini Configured:', bool(settings.GEMINI_API_KEY), '| Sarvam Configured:', bool(settings.SARVAM_API_KEY), '| DB Configured:', bool(settings.DATABASE_URL))"
```
