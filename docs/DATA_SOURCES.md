# Authoritative Data Sources, Ingestion Pipelines & Integrations

> **Phase 2 Status**: Fully implemented. Core data ingestion pipelines, official government scheme seeder, pgvector knowledge chunking engine, and Data.gov.in Agmarknet mandi price provider are implemented, tested, and verifiable.

---

## 1. Summary of Implemented Integrations

| Data Domain | Provider Class / Script | Source Authority | Data Origin Tag | Authentication / Key |
| :--- | :--- | :--- | :--- | :--- |
| **Market Mandi Prices** | `AgmarknetMandiProvider` in `backend/app/providers/mandi_provider.py` | Data.gov.in (Agmarknet 2.0 Daily Arrivals) | `production_live` / `production_cached` | `DATA_GOV_IN_API_KEY` (Free OGD key) |
| **Central Welfare Schemes** | `scripts/seed_government_schemes.py` | Official Portals (pmkisan.gov.in, pmfby.gov.in, myscheme.gov.in, soilhealth.dac.gov.in) | `production_live` | None (Public Domain Records) |
| **Agricultural Knowledge Base** | `scripts/ingest_agricultural_knowledge.py` | ICAR (IIRR, IARI, CICR) & SAUs (ANGRAU, PAU, UAS Bangalore) | `production_live` | None (Public Package of Practices) |
| **Vector Embeddings (768-dim)** | `GeminiEmbeddingProvider` / `DeterministicMockEmbeddingProvider` | Google Gemini `text-embedding-004` (with fallback mock for offline dev) | System Vector | `GEMINI_API_KEY` / `LLM_API_KEY` |

---

## 2. Ingestion Commands & Automation

### 2.1 Government Welfare Schemes Seeding
Populates verified schemes idempotently into `government_schemes` and logs metrics into `sync_logs`:
```bash
python scripts/seed_government_schemes.py
```
- **Seeded Initial Schemes**:
  1. `PM_KISAN` — Pradhan Mantri Kisan Samman Nidhi (`https://pmkisan.gov.in`)
  2. `PMFBY` — Pradhan Mantri Fasal Bima Yojana (`https://pmfby.gov.in`)
  3. `KCC` — Kisan Credit Card Scheme (`https://myscheme.gov.in/schemes/kcc`)
  4. `SOIL_HEALTH_CARD` — Soil Health Card Scheme (`https://soilhealth.dac.gov.in`)
  5. `PMKSY_PDMC` — PMKSY Per Drop More Crop (`https://pmksy.gov.in`)
- **Fields Stored**: `scheme_name`, `name_translations`, `short_description`, `benefits_summary`, `eligibility_criteria` (JSON list), `required_documents` (JSON list), `application_process`, `official_portal_url`, `sponsoring_agency`, `state_scope`, `last_verified_date`.

### 2.2 Authoritative Agricultural Knowledge Ingestion
Extracts, cleans, chunks, hashes, and embeds Package of Practices publications into `source_documents` and `knowledge_chunks`:
```bash
python scripts/ingest_agricultural_knowledge.py
```
- **Initial Authoritative Sources**:
  1. *ICAR-IIRR*: Yellow Stem Borer & BPH Integrated Pest Management in Paddy (`https://icar-iirr.org/advisory/pop_rice_ipm_2024.pdf`)
  2. *ICAR-IARI*: Wheat Sowing Window, Irrigation Schedule (CRI stage), & Yellow Rust Prevention (`https://iari.res.in/technologies/wheat_production_guide_2024.pdf`)
  3. *ANGRAU*: Chili Thrips & Murda (Leaf Curl) Complex Management (`https://angrau.ac.in/advisories/chili_thrips_murda_protocol.pdf`)
  4. *ICAR-CICR*: Cotton Pink Bollworm & Sucking Pest Guidelines (`https://cicr.org.in/advisories/cotton_ipm_guidelines_2024.pdf`)
  5. *PAU*: Raya (Mustard) Nutrient & Aphid Control (`https://pau.edu/pop/oilseeds_mustard_2024.pdf`)
  6. *UAS Bangalore*: Finger Millet (Ragi) Blast Disease & Rainfed Practices (`https://uasbangalore.edu.in/pop/millets_ragi_guide_2024.pdf`)
- **Chunking Parameters**: Max 400 tokens, 50-token overlap, paragraph & header boundary preservation, deterministic SHA-256 `content_hash`, and sequential `chunk_index`.

---

## 3. Mandi Price Integration & Freshness Rules

### 3.1 Agmarknet Provider Architecture (`AgmarknetMandiProvider`)
- **API Endpoint**: `https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070`
- **Normalization**:
  - `arrival_date`: Safely parsed from government date formats (`DD/MM/YYYY`, `YYYY-MM-DD`) into ISO `YYYY-MM-DD`.
  - `min_price`, `max_price`, `modal_price`: Cast to `float` (₹/Quintal).
  - `fetched_at`: Precise UTC timestamp when the API call was made.

### 3.2 Strict Freshness & Truthfulness Standard
- **Never claim an arrival date is "today" merely because it was fetched today.** The UI and API strictly expose both `arrival_date` (market transaction date) and `fetched_at` (audit sync date).
- **Data Origin Classifications**:
  - `production_live`: Freshly retrieved from Data.gov.in during the current request.
  - `production_cached`: Retrieved from local PostgreSQL cache when upstream API is slow, rate-limited, or unavailable.
  - `development_seed`: Local fixtures for development; never presented as authoritative government data.

### 3.3 Caching & Fallback Behavior
1. Live fetch attempted first if `DATA_GOV_IN_API_KEY` is provided.
2. Successful pulls are upserted into `mandi_prices` table with `data_origin="production_live"`.
3. If upstream times out or returns HTTP 5xx: queries database for latest records matching state/district/commodity, tagging them as `production_cached`.
4. If no records exist: returns an empty result with zero fabricated records.

---

## 4. Ingestion Audit Logs (`sync_logs`)

Every ingestion and seeding run writes an audit entry:
- `sync_source`: e.g., `ICAR_POP_INGEST`, `MYSCHEME_SCRAPE`, `AGMARKNET_DATA_GOV_IN`
- `status`: `SUCCESS`, `FAILED`, `PARTIAL`
- `records_processed`, `records_inserted`, `records_updated`
- `execution_time_seconds`: Runtime duration
- `error_message`: Sanitized error text (zero API keys or secrets logged)

---

## 5. Known Limitations & Next Steps
- **Live Agmarknet Key Required for Real-Time Mandi Data**: When running without `DATA_GOV_IN_API_KEY`, the provider relies on cached records in `mandi_prices`. A free key from `data.gov.in` enables live pulls.
- **Next Phase (Phase 3)**: Implement Indian regional language voice processing (Sarvam AI STT & TTS).
