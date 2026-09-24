# Database Architecture & Supabase / PostgreSQL Schema

> **Phase 2 Status**: Migrations verified and applied. Database seeded with 6 authoritative source documents, 26 knowledge chunks, 5 government schemes, and audit sync logs.

---

## 1. Migration History

### Migration 1: `20260922000000_initial_schema.sql`
- Creates 10 core tables (`farmer_profiles`, `farmer_crops`, `conversations`, `query_logs`, `response_logs`, `source_documents`, `knowledge_chunks`, `government_schemes`, `mandi_prices`, `sync_logs`).
- Enables `uuid-ossp`, `pgcrypto`, and `vector` extensions.
- Configures HNSW vector index (`vector_cosine_ops`) for `knowledge_chunks.embedding vector(768)`.
- Implements `update_timestamp()` trigger for `updated_at` columns.

### Migration 2: `20260922000001_phase2_provenance_and_chunking.sql`
- Enhances `source_documents` with:
  - `source_name VARCHAR(150)`
  - `content_hash VARCHAR(64) UNIQUE`
  - `fetched_at TIMESTAMPTZ`
  - `language VARCHAR(10)`
  - `metadata JSONB`
- Enhances `knowledge_chunks` with:
  - `chunk_index INT NOT NULL DEFAULT 0` (preserves sequential document order)
- Adds indexes on `source_documents(content_hash)` and `knowledge_chunks(document_id, chunk_index)`.

---

## 2. Table Specifications & Active Records

| Table Name | Description | Key Constraints | Phase 2 Records |
| :--- | :--- | :--- | :--- |
| `source_documents` | Authoritative publications (ICAR, SAU, KVK) | UUID PK, `content_hash` UNIQUE, non-null authority | 6 publications |
| `knowledge_chunks` | Agronomic advice chunks with 768-dim embeddings | UUID PK, FK to `source_documents`, HNSW index, `chunk_index` | 26 chunks |
| `government_schemes` | Central and state welfare schemes | UUID PK, `scheme_code` UNIQUE, non-null portal URL | 5 central schemes |
| `mandi_prices` | Market arrival prices from Agmarknet | UUID PK, composite unique key on market/commodity/date | Cached on pull |
| `sync_logs` | Ingestion and sync audit logs | UUID PK, provider name, status, duration | 4+ audit logs |
| `farmer_profiles` | Farmer profile and location | UUID PK, `session_id` UNIQUE | Phase 1 schema |
| `farmer_crops` | Farmer active crops | UUID PK, FK to `farmer_profiles` | Phase 1 schema |
| `conversations` | Consultation conversations | UUID PK, FK to `farmer_profiles` | Phase 1 schema |
| `query_logs` | Farmer queries | UUID PK, FK to `conversations` | Phase 1 schema |
| `response_logs` | Grounded responses & citations | UUID PK, FK to `query_logs` UNIQUE | Phase 1 schema |

---

## 3. Idempotency & Deduplication Architecture

1. **Source Documents**: Deduplicated by SHA-256 `content_hash` of document text. Repeated runs of `ingest_agricultural_knowledge.py` skip existing documents without re-inserting.
2. **Knowledge Chunks**: Matched by `(document_id, content_hash)`. Existing chunks are updated with fresh timestamps rather than duplicated.
3. **Government Schemes**: Deduplicated by `scheme_code` (e.g. `PM_KISAN`, `PMFBY`). Repeated runs update fields idempotently.
4. **Mandi Prices**: Enforces `CONSTRAINT unique_mandi_record UNIQUE (state, district, market, commodity, variety, arrival_date)`.
