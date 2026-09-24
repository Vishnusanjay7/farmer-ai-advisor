# Retrieval-Augmented Generation (RAG) Architecture & Grounding Guardrails

> **Phase 4 Status**: Complete 10-layer conversational RAG pipeline implemented and verified. Specialized intent routing (`CROP_ADVISORY`, `PEST_DISEASE`, `MANDI_PRICE`, `GOVERNMENT_SCHEME`, `UNSUPPORTED`), 768-dim dense embedding vector search, pre-LLM threshold gating (threshold $\ge 0.55$), official `gemini-3.8-flash` LLM provider, post-generation grounding heuristic validation, and automatic safe abstention active across 83 automated test cases.

## 1. RAG Philosophy & Grounding Policy
In critical domains like agriculture, an ungrounded model making unsupported chemical dosage or disease claims can lead to crop damage, soil degradation, or financial distress for farmers.

Therefore, our RAG pipeline strictly enforces:
1. **No Unsupported Factual Claim May Be Presented as Verified:** Agricultural factual responses must be grounded exclusively in authoritative retrieved sources (ICAR, SAU, Agmarknet, myScheme), and the system must abstain when sufficient evidence is unavailable.
2. **The LLM is a Synthesizer and Translator, NOT an Autonomous Knowledge Base.**
3. **Context is King:** If a fact (chemical name, dosage, eligibility criteria, mandi rate) does not exist in the retrieved authoritative chunks, the LLM is explicitly instructed to abstain rather than speculate.
4. **Authoritative Source Provenance:** Every response must retain and cite its authoritative source (agency, publication, section/page).
5. **Extensible Agronomic Taxonomy:** The knowledge architecture is not limited to fixed crops. It supports arbitrary crops, agro-climatic zones, and regions through extensible metadata attributes (`crop_name`, `state`, `language`, `season`, `growth_stage`, `topic`, `source_date`, `updated_at`).

---

## 2. Ingestion & Document Processing Pipeline

```
  Authoritative Agricultural PDFs / Manuals / Guidelines
  (ICAR PoP, State Agricultural Universities, CIBRC Pesticide Manuals, myScheme Docs)
                                    │
                                    ▼
                        [Document Ingestion Worker]
                                    │
                        ┌───────────┴───────────┐
                        ▼                       ▼
              [Document Normalizer]    [Metadata Extractor]
             - Clean header/footers    - Sponsoring Agency
             - Unicode normalization   - Agro-climatic Zone
             - Table markdown parsing  - Target Crop & Topic
                                    │
                                    ▼
                       [Hierarchical Chunking Engine]
                    - Chunk Size: 400-500 tokens
                    - Overlap: 80 tokens
                    - Boundaries: Strict split on Heading / Section / Table
                                    │
                                    ▼
                     [Embedding Generator (Gemini/OpenAI)]
                     - text-embedding-004 (768 dimensions)
                                    │
                                    ▼
               [Storage in Supabase/Postgres with pgvector]
             - Chunks stored in `knowledge_chunks`
             - Full-Text search vector generated automatically (`to_tsvector`)
             - HNSW index updated
```

### Chunk Metadata Structure
Each chunk stored in `knowledge_chunks` contains:
```json
{
  "document_id": "8c4f1e00-2d55-46a1-b844-3290b8f3d61a",
  "crop_name": "Paddy",
  "topic": "Integrated Pest Management",
  "pest_or_disease": "Yellow Stem Borer",
  "stage": "Tillering to Panicle Initiation",
  "issuing_authority": "ICAR - Indian Institute of Rice Research (IIRR)",
  "state_applicability": "All-India",
  "publication_year": 2024,
  "chemical_mentions": ["Chlorantraniliprole", "Cartap Hydrochloride"],
  "organic_alternatives": ["Trichogramma japonicum", "Neem oil 1500 ppm"]
}
```

---

## 3. Query Processing & Hybrid Retrieval

When a farmer query arrives, the system does not simply send raw text to an embedding search. It follows a multi-stage retrieval strategy:

```
                  Farmer Transcript / Text
                            │
                            ▼
              [Query Expander & Entity Extractor]
          - Extracted Entities: Crop=Paddy, Pest=Stem Borer, District=Warangal
          - Farmer Context Added: State=Telangana, Soil=Red Sandy Loam
                            │
            ┌───────────────┴───────────────┐
            ▼                               ▼
    [Dense Vector Search]          [Sparse Keyword Search]
    pgvector Cosine Similarity     Postgres TSVECTOR GIN Search
    (Captures semantic nuances,    (Matches exact Latin/chemical
     symptoms, dialect variations)  names, pest names, crop varieties)
            │                               │
            └───────────────┬───────────────┘
                            ▼
           [Reciprocal Rank Fusion (RRF) & Re-ranking]
     Score = 0.65 * Vector_Similarity + 0.35 * BM25_Score
                            │
                            ▼
               [Relevance Score Threshold]
            Is Max_Score >= 0.72?
                   ├── YES ──> Pass to Grounded Generation
                   └── NO  ──> Trigger Safe Refusal / Advisory Fallback
```

### Retrieval Query Example (SQL):
```sql
WITH vector_matches AS (
    SELECT 
        kc.id,
        kc.content,
        kc.metadata,
        sd.title AS source_title,
        sd.issuing_authority,
        sd.publication_year,
        sd.official_document_url,
        1 - (kc.embedding <=> :query_vector) AS vector_similarity
    FROM knowledge_chunks kc
    JOIN source_documents sd ON kc.document_id = sd.id
    WHERE kc.crop_name ILIKE :crop_entity OR kc.crop_name IS NULL
    ORDER BY kc.embedding <=> :query_vector
    LIMIT 10
),
text_matches AS (
    SELECT 
        kc.id,
        ts_rank_cd(kc.search_tsv, plainto_tsquery('english', :search_terms)) AS text_rank
    FROM knowledge_chunks kc
    WHERE kc.search_tsv @@ plainto_tsquery('english', :search_terms)
    LIMIT 10
)
SELECT 
    v.*,
    COALESCE(t.text_rank, 0.0) AS text_score,
    (0.65 * v.vector_similarity + 0.35 * COALESCE(t.text_rank, 0.0)) AS combined_score
FROM vector_matches v
LEFT JOIN text_matches t ON v.id = t.id
WHERE (0.65 * v.vector_similarity + 0.35 * COALESCE(t.text_rank, 0.0)) >= 0.68
ORDER BY combined_score DESC
LIMIT 4;
```

---

## 4. Grounded Prompt Engineering & Safety Guardrails

The LLM receives a strictly constrained prompt template:

```markdown
You are the Official Agricultural AI Advisor for Indian Farmers.
Your duty is to assist farmers with 100% verified, safe, and factual guidance.

CRITICAL SAFETY RULES:
1. ONLY use information provided in the [VERIFIED OFFICIAL CONTEXT] below.
2. If the context does not specify a pesticide dosage, treatment method, or scheme detail, DO NOT INVENT IT. Explicitly state that official records for that specific detail are not available and advise consulting the nearest Krishi Vigyan Kendra (KVK).
3. Do NOT invent pesticide formulations, brand names, or chemical ratios.
4. When stating chemical advice, always mention safety protective gear (gloves, mask) and non-chemical/biological alternatives first if present in the context.
5. Every single answer must conclude with an attribution stating the issuing authority and document name.
6. Respond in the farmer's requested language ({language_name}) with warm, polite, and simple terminology that a rural farmer understands.

[FARMER PROFILE]:
State: {state} | District: {district} | Land: {land_acres} Acres | Crops: {crops}

[VERIFIED OFFICIAL CONTEXT]:
{context_chunks}

[FARMER QUERY]:
{user_query}
```

---

## 5. Post-Generation Citation & Hallucination Gatekeeper
Before the synthesized response is returned to the user or sent to Text-to-Speech:
1. **Chemical Name Validation:** The backend scans the LLM's generated response for any pesticide/chemical entities. If a chemical is mentioned that was NOT present in `[VERIFIED OFFICIAL CONTEXT]`, the response is immediately rejected and replaced with the safe refusal fallback.
2. **Numeric Dosage Check:** If numerical dosage figures (e.g., `2 ml/L` or `400 g/acre`) appear in the text, regex verification confirms they match the retrieved chunk figures.
3. **Structured Attribution Tagging:** Sources are packaged as structured JSON objects for the frontend UI to display clickable verification badges.
