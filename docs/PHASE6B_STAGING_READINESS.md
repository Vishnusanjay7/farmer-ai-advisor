# Phase 6B — Staging & Production Readiness Specification

**Project**: Regional Language Voice-Based AI Advisory Assistant for Small and Marginal Farmers Using Government Agricultural Data  
**Document**: Staging & Production Deployment Readiness Guide  
**Status**: Pre-Deployment Verification Complete (No cloud infrastructure is currently provisioned or deployed).

---

## 1. Environment Classification & Strategy

The application architecture explicitly supports three operational tiers:

| Attribute | Local Development | Staging Environment | Production Environment |
| :--- | :--- | :--- | :--- |
| **`ENVIRONMENT`** | `development` | `staging` | `production` |
| **`DEBUG`** | `true` (Swagger docs enabled) | `false` (API docs disabled) | `false` (API docs disabled) |
| **Database** | SQLite fallback (`farmer_dev.db`) | Supabase PostgreSQL (`vector(768)`) | Supabase PostgreSQL (`vector(768)`) |
| **Silent SQLite Fallback** | Permitted for developer agility | **REJECTED** (Fails startup if unset) | **REJECTED** (Fails startup if unset) |
| **AI Providers** | Mock providers if keys unset | Live Gemini & Sarvam APIs | Live Gemini & Sarvam APIs |
| **Mock LLM Fallback** | Permitted in offline tests | **REJECTED** (Must fail if key missing) | **REJECTED** (Must fail if key missing) |
| **CORS Origins** | `localhost:3000`, `127.0.0.1:3000` | Staging Vercel URL (e.g., `*.vercel.app`) | Locked Production URL (No `*`) |
| **CORS Wildcard (`*`)** | Prohibited | **REJECTED** | **REJECTED** |
| **Rate Limiting** | Active (Instance-local) | Active (Instance-local) | Active (Instance-local) |
| **Reverse Proxy Header** | `TRUST_PROXY_HEADERS=false` | `TRUST_PROXY_HEADERS=false` (safe default) | `TRUST_PROXY_HEADERS=false` (safe default) |
| **Frontend URL** | `http://localhost:8000` | Staging Render Backend URL | Production Render/Custom Backend URL |
| **Data Origin Policy** | `development_seed` allowed in test | `production_live` / `production_cached` only | `production_live` / `production_cached` only |

---

## 2. Environment Variables Matrix

All variables are strictly partitioned between server-side backend services (Render / Railway) and client-side web bundles (Vercel).

### 2.1 Backend Server-Side Configuration (Render / Railway)

| Variable | Required in Prod/Staging? | Secret? | Type / Value Example | Scope & Purpose |
| :--- | :---: | :---: | :--- | :--- |
| `ENVIRONMENT` | **YES** | No | `staging` or `production` | Activates strict security validations. |
| `DEBUG` | **YES** | No | `false` | Disables `/docs`, `/redoc`, and stack traces. |
| `LOG_LEVEL` | No | No | `INFO` | Configures structured logging verbosity. |
| `BACKEND_HOST` | **YES** | No | `0.0.0.0` | Binds server to all container network interfaces. |
| `BACKEND_PORT` | **YES** | No | `8000` (or `$PORT`) | Injected automatically by PaaS host. |
| `ALLOWED_ORIGINS` | **YES** | No | `https://farmer-ai-advisor.vercel.app` | CSV of authorized frontend web origins. |
| `DATABASE_URL` | **YES** | **YES** | `postgresql://postgres.[ref]:[pass]@...:5432/postgres` | Supabase PostgreSQL Session Pooler connection URI. |
| `SARVAM_API_KEY` | **YES** | **YES** | `sk_live_...` | Sarvam AI key for Saaras v3 STT and Bulbul v3 TTS. |
| `SARVAM_STT_ENDPOINT` | No | No | `https://api.sarvam.ai/speech-to-text` | Official REST endpoint for regional STT. |
| `SARVAM_TTS_ENDPOINT` | No | No | `https://api.sarvam.ai/text-to-speech` | Official REST endpoint for regional TTS. |
| `LLM_PROVIDER` | **YES** | No | `gemini` | Grounded advisory synthesis provider. |
| `GEMINI_API_KEY` | **YES** | **YES** | `AIzaSy...` | Google AI Studio Gemini API key. |
| `LLM_MODEL` | **YES** | No | `gemini-3.8-flash` | Approved Gemini Flash model identifier. |
| `EMBEDDING_PROVIDER` | **YES** | No | `gemini` | Embeddings provider for 768-dim vector space. |
| `EMBEDDING_MODEL` | **YES** | No | `gemini-embedding-001` | Current approved Gemini embedding model supporting 768-dim output. |
| `EMBEDDING_DIMENSION` | **YES** | No | `768` | Must match PostgreSQL `vector(768)` schema. |
| `RAG_TOP_K` | No | No | `4` | Number of authoritative chunks retrieved. |
| `RAG_SIMILARITY_THRESHOLD` | No | No | `0.55` | Strict pre-LLM evidence relevance gate. |
| `DATA_GOV_IN_API_KEY` | **YES** | **YES** | `579b464db66ec23bdd...` | Data.gov.in key for live Agmarknet mandi sync. |
| `AGMARKNET_RESOURCE_ID` | **YES** | No | `9ef84268-d588-465a-a308-a864a43d0070` | OGD resource ID for daily market arrivals. |
| `AGMARKNET_CACHE_TTL_SECONDS` | No | No | `21600` | 6 hours cache freshness threshold. |
| `RATE_LIMIT_ENABLED` | **YES** | No | `true` | Enables in-memory quota enforcement. |
| `TRUST_PROXY_HEADERS` | No | No | `false` | Safe default. When false, ignores X-Forwarded-For to prevent IP spoofing. |
| `MAX_AUDIO_UPLOAD_SIZE_MB` | No | No | `15` | Upper bound for uploaded voice audio. |
| `ENABLE_MOCK_FALLBACK` | No | No | `true` | Allows deterministic offline fallback if API keys drop. |

### 2.2 Frontend Client-Side Configuration (Vercel)

| Variable | Required? | Secret? | Value Example | Notes |
| :--- | :---: | :---: | :--- | :--- |
| `NEXT_PUBLIC_BACKEND_URL` | **YES** | **NO (Public)** | `https://farmer-ai-advisor-backend.onrender.com` | Base URL used by browser to query backend REST APIs. |

> [!CAUTION]
> **Zero Secret Leakage Boundary**: `GEMINI_API_KEY`, `SARVAM_API_KEY`, `DATA_GOV_IN_API_KEY`, and `DATABASE_URL` must NEVER be placed in Vercel or given the `NEXT_PUBLIC_` prefix. The Next.js frontend interacts exclusively with our FastAPI backend proxy.

---

## 3. Supabase PostgreSQL & pgvector Requirements

### 3.1 Extensions Required
1. `uuid-ossp`: For generating UUID primary keys.
2. `pgcrypto`: For cryptographic hashing and token verification.
3. `vector`: pgvector extension supporting dense 768-dimensional float arrays and cosine similarity.

### 3.2 Migration Execution Order
Execute the following two idempotent migrations sequentially:
1. `supabase/migrations/20260922000000_initial_schema.sql`:
   - Creates 10 core tables: `farmer_profiles`, `farmer_crops`, `conversations`, `query_logs`, `response_logs`, `source_documents`, `knowledge_chunks`, `government_schemes`, `mandi_prices`, and `sync_logs`.
   - Creates HNSW index: `idx_knowledge_chunks_embedding_hnsw` on `knowledge_chunks(embedding vector_cosine_ops)` with parameters `(m = 16, ef_construction = 64)`.
   - Attaches `update_timestamp()` triggers.
2. `supabase/migrations/20260922000001_phase2_provenance_and_chunking.sql`:
   - Adds provenance tracking: `source_name`, `content_hash`, `fetched_at`, `language`, and `metadata` to `source_documents`.
   - Adds `chunk_index` to `knowledge_chunks` for section ordering.

### 3.3 Database Seeding (Post-Migration)
Once migrations are executed:
```bash
# 1. Seed 5 verified Central Government schemes
python scripts/seed_government_schemes.py

# 2. Ingest 6 verified ICAR/SAU publications (26 chunks with 768-dim embeddings)
python scripts/ingest_agricultural_knowledge.py
```

### 3.4 Data Origin Enforcement
- Staging and production strictly enforce:
  - `production_live`: Live fetched records from Agmarknet.
  - `production_cached`: Authoritative records stored in PostgreSQL within cache validity window.
  - `development_seed`: Strictly excluded by `retrieval_service.py` (`data_origin IN ('production_live', 'production_cached')`).

### 3.5 Vector Compatibility & Ingestion Safety
- **Vector Model Homogeneity**: Vectors from different embedding models (or between live Gemini models and mock hash vectors) are mathematically disjoint and must NEVER be mixed within the database.
- **Re-Embedding Invariant**: Changing the embedding model in the future strictly requires re-embedding the entire knowledge corpus (all 26 chunks).
- **Pre-Ingestion Status**: Because the Supabase staging database currently contains only the schema with zero authoritative knowledge chunks, setting `EMBEDDING_MODEL=gemini-embedding-001` prior to ingestion prevents any future vector migration or mixed coordinate space issues.
- **Fail-Closed Gate**: In `staging` and `production`, `get_embedding_provider()` and `RetrievalService` raise explicit `ValueError` if `GEMINI_API_KEY` is missing, preventing any silent fallback to `DeterministicMockEmbeddingProvider`.

---

## 4. Security & CORS Configuration

### 4.1 CORS Enforcement
- Production/staging strictly rejects wildcard `*`.
- Allowed origins must match the exact HTTPS domain of the Vercel staging/production deployment (e.g. `https://farmer-ai-advisor.vercel.app`).
- Multiple origins can be supplied as a comma-separated list and are parsed automatically into `List[str]`.

### 4.2 HTTPS Mandatory for Voice
- Modern browsers strictly disallow `navigator.mediaDevices.getUserMedia` on non-secure origins (HTTP).
- Both frontend (Vercel) and backend (Render) enforce HTTPS via Let's Encrypt automated TLS certificates.

---

## 5. Instance-Local Rate Limiting Safeguards

The system operates an in-memory sliding window rate limiter (`InMemoryRateLimiter`):

- `POST /api/v1/voice/stt`: **10 requests / minute / client IP**
- `POST /api/v1/voice/tts`: **10 requests / minute / client IP**
- `POST /api/v1/advisor/query`: **20 requests / minute / client IP**
- `GET /api/v1/mandi/prices`: **30 requests / minute / client IP**
- `GET /api/v1/health`: **60 requests / minute / client IP**

### 5.1 Architecture & Limitations
- **Instance-Local Protection**: State is tracked in-process within `collections.deque` and bounded to 10,000 keys.
- **Why Redis was Excluded**: Avoids operational complexity, external network latency, and single-point-of-failure risks during hackathon evaluation.
- **Horizontal Scaling Limitation**: If deployed with $N$ replica containers behind a round-robin load balancer without sticky sessions, effective rate limits scale to $N \times \text{limit}$. This is documented and accepted.

### 5.2 Reverse-Proxy Headers & Client IP Resolution (`TRUST_PROXY_HEADERS`)
- **Safe Default (`TRUST_PROXY_HEADERS=false`)**:
  - `false` is the safe default across all environments (local development, staging, and production).
  - When `TRUST_PROXY_HEADERS=false`, the rate limiter resolves client IP strictly from direct TCP connection metadata (`request.client.host`).
- **Risk of Blind Trust**:
  - `X-Forwarded-For` must NOT be trusted blindly. If an application blindly trusts proxy headers without a strictly configured upstream reverse proxy that overwrites/strips untrusted client headers, an attacker can easily forge headers (e.g., `X-Forwarded-For: 1.2.3.4`) to evade rate limits or cause IP spoofing.
- **Deployment-Specific Decision**:
  - Enabling `TRUST_PROXY_HEADERS=true` is an explicit, deployment-specific decision that must only occur after the selected hosting platform's reverse proxy behavior (e.g., Render, Railway, AWS ALB, Cloudflare) has been empirically verified to sanitize incoming headers.
  - Neither Render nor Railway proxy header behavior has been live-verified in this repository.
  - For generic staging configuration, the default recommendation is `TRUST_PROXY_HEADERS=false`.
- **Rate Limiting Invariant**:
  - The instance-local sliding window algorithm, endpoints, thresholds (STT 10/min, TTS 10/min, Advisor 20/min, Mandi 30/min, Health 60/min), and RFC7807 responses remain completely unchanged regardless of the `TRUST_PROXY_HEADERS` toggle.

---

## 6. Startup, Health & Readiness Strategy

- **Lightweight Health Ping (`GET /api/v1/health`)**:
  - Responds in < 10ms with `{"status": "ok", "service": "farmer-ai-backend", "version": "0.1.0"}`.
  - Intentionally decoupled from database queries and external third-party AI APIs to prevent health check flapping during transient provider hiccups.
- **Sanitized Logging & Error Handling**:
  - `SecretSanitizingFormatter` scrubs tokens, passwords, and API keys matching sensitive regex patterns.
  - Advisor endpoint wraps all internal exceptions into standardized RFC7807 problem details with zero stack trace leakage.

---

## 7. Rollback & Disaster Recovery Procedures

1. **Frontend Rollback (Vercel)**:
   - Go to Vercel Project Dashboard -> Deployments.
   - Click "Promote to Production" on the previous working deployment for instant zero-downtime rollback.
2. **Backend Rollback (Render / Railway)**:
   - Go to Render Dashboard -> Web Service -> Deploys.
   - Click "Rollback to this deploy" on the previously verified commit.
3. **Database Recovery (Supabase)**:
   - Supabase provides automated Point-in-Time Recovery (PITR) and daily backups.
   - In case of schema issues, migration additions are non-destructive and can be reverted by dropping added columns without touching core records.
4. **Provider Fallback**:
   - If external APIs (Sarvam or Data.gov.in) experience transient downtime, `ENABLE_MOCK_FALLBACK=true` allows the system to gracefully serve cached verified agricultural advice and clear abstentions without crashing.
