# HackWave Architecture Diagrams (Editable Presentation Style)

This directory contains the production-accurate architecture and data diagrams for **KrishiVaani (Farmer AI Advisor)**, built for the HackWave Hackathon.

All diagrams are designed in a **presentation-ready, editable PowerPoint (PPT) style**:
- **White Background (`#FFFFFF`)**: Clean, light theme suitable for presentations, pitch decks, and Figma.
- **White Box Interiors (`fill="#FFFFFF"`)**: Uncluttered, crisp cards with clean white background.
- **Color-Coded Box Outlines**: Vibrant, distinct colored strokes per subsystem (Green, Blue, Purple, Teal, Amber, Red, Cyan).
- **Color-Coded Text**: Headers and badges match subsystem theme colors with high-contrast readable dark text for descriptions.
- **Native Editable PowerPoint Files (`.pptx`)**: Pre-built native PowerPoint shapes and text boxes that you can open and edit immediately in Microsoft PowerPoint, Google Slides, or Keynote!
- **High-Resolution Vector (`.svg`) & Raster (`.png`) Previews**: Scalable SVGs (convertible to native PowerPoint shapes via "Convert to Shape") and 2x crisp PNG images.

---

## Directory Structure

```
hackathon-diagrams/
├── hackwave-diagrams.pptx                # Master 3-Slide Editable PowerPoint Presentation
├── README.md                             # Documentation & Validation Report
├── system-architecture/
│   ├── system-architecture.svg           # Scalable Vector Diagram (White Theme)
│   ├── system-architecture.png           # 2x High-Resolution Raster Preview
│   └── system-architecture.pptx          # Native Editable PowerPoint Slide
├── end-to-end-workflow/
│   ├── end-to-end-workflow.svg           # Scalable Vector Diagram (White Theme)
│   ├── end-to-end-workflow.png           # 2x High-Resolution Raster Preview
│   └── end-to-end-workflow.pptx          # Native Editable PowerPoint Slide
└── er-diagram/
    ├── er-diagram.svg                    # Scalable Vector Diagram (White Theme)
    ├── er-diagram.png                    # 2x High-Resolution Raster Preview
    └── er-diagram.pptx                   # Native Editable PowerPoint Slide
```

---

## 1. System Architecture

- **Files**:
  - `system-architecture/system-architecture.svg`
  - `system-architecture/system-architecture.png`
  - `system-architecture/system-architecture.pptx`
- **Dimensions**: 1400 × 820 px (landscape)
- **Palette**:
  - **Farmer & Speech Interface**: Emerald Green (`#16A34A`) & Cyan (`#0284C7`) outlines.
  - **FastAPI Backend Orchestration**: Deep Blue (`#2563EB`) & Indigo (`#4F46E5`) outlines.
  - **Knowledge Retrieval & Routing**: Royal Purple (`#7C3AED`) outline.
  - **Authoritative Data & Supabase**: Teal (`#0D9488`) & Amber (`#D97706`) outlines.
  - **Abstention & Safety**: Crimson Red (`#DC2626`) outline.
  - **Reasoning Layer (Gemini LLM)**: Violet (`#6366F1`) outline.
- **Architecture Highlights**:
  1. **Farmer Input**: Multimodal entry point (Voice or Text) with BCP-47 language tag (`hi-IN`, `te-IN`, `mr-IN`, etc.).
  2. **Speech Recognition**: Sarvam AI STT (`saaras:v3`) for voice queries.
  3. **FastAPI Backend**: Orchestration, request validation, request ID tracking, and pipeline coordination.
  4. **Query Preprocessing & Intent**: Unicode NFKC normalization, regex keyword intent classification (6 intents), context extraction (crop, state, season, growth stage).
  5. **3 Parallel Retrieval Paths**:
     - *Crop / Pest / General Agri*: Hybrid Vector + Keyword Search against `knowledge_chunks` with 768-dim embeddings via Supabase pgvector (`match_chunks`).
     - *Government Schemes*: Structured querying against `government_schemes` table.
     - *Mandi Prices*: Structured lookup against `mandi_prices` APMC table.
  6. **Authoritative Ground Truth**:
     - Official sources: **ICAR / State Agricultural Universities**, **MoAFW Government Scheme Data**, **Agmarknet / Data.gov.in**.
     - *"Official agricultural data is the source of truth; AI retrieves, validates, and communicates it."*
  7. **Abstention Boundary**: Insufficient retrieval evidence bypasses the LLM and issues a safe abstention response with the Kisan Call Center helpline (`1800-180-1551`).
  8. **Reasoning & Synthesis**: Gemini LLM operates strictly as a reasoning and linguistic layer constrained by retrieved evidence.
  9. **Delivery**: Final response with source citations, delivered as text and optional Sarvam AI TTS (`bulbul:v3`) voice audio.

---

## 2. End-to-End Workflow

- **Files**:
  - `end-to-end-workflow/end-to-end-workflow.svg`
  - `end-to-end-workflow/end-to-end-workflow.png`
  - `end-to-end-workflow/end-to-end-workflow.pptx`
- **Title**: *"Farmer Query → Grounded Agricultural Response"*
- **Dimensions**: 1300 × 900 px (landscape)
- **Workflow Highlights**:
  - **S1–S2**: Multi-modal query capture (Voice ? Yes → Sarvam STT : No → Text Query).
  - **S3–S5**: Preprocessing, regex/keyword classification, and context metadata extraction.
  - **S6**: Multi-way routing branch:
    - *Crop/Pest/Agri*: Vector + Keyword Retrieval → Evidence Check.
    - *Government Scheme*: Government Scheme Structured Data.
    - *Mandi Price*: Mandi Structured Data.
    - *Unsupported*: Safe refusal response.
    - *Insufficient Evidence*: Safe multilingual abstention.
  - **S7–S9**: Evidence assembly, Gemini LLM reasoning (explicitly marked as NOT the data source), grounding and citation validation.
  - **S10**: Final response formatting with source metadata and optional Sarvam TTS voice synthesis.
  - **Critical Rule Callout**: Prominent amber box reinforcing that Gemini is strictly the reasoning layer and not the source of truth.

---

## 3. Entity-Relationship (ER) Diagram

- **Files**:
  - `er-diagram/er-diagram.svg`
  - `er-diagram/er-diagram.png`
  - `er-diagram/er-diagram.pptx`
- **Dimensions**: 1500 × 900 px (landscape)
- **Source Migrations**: Verified against `20260922000000_initial_schema.sql` and `20260922000001_phase2_provenance_and_chunking.sql`.
- **Implemented Tables**:
  1. `farmer_profiles`: Farmer registry with language preference, state, and district (Green outline).
  2. `farmer_crops`: Crops cultivated by farmers, sowing date, area acres (FK to `farmer_profiles.id`).
  3. `conversations`: Multi-turn session container (FK to `farmer_profiles.id`, Blue outline).
  4. `query_logs`: Incoming query logging with intent and context metadata (FK to `conversations.id`).
  5. `response_logs`: Outgoing advisor responses, grounding confidence score, latency, and tokens (FK to `query_logs.id`).
  6. `source_documents`: Authoritative documents from ICAR/Govt with version, checksum, and status (Purple outline).
  7. `knowledge_chunks`: Text chunks with 768-dim `vector(768)` embeddings, token counts, and chunk index (FK to `source_documents.id`).
  8. `government_schemes`: State and central government agricultural schemes with eligibility criteria (Teal outline).
  9. `mandi_prices`: Daily APMC market commodity prices, varieties, and modal rates (Teal outline).
  10. `sync_logs`: Audit log for background data ingestion and syncing pipelines (Amber outline).
- **Relationships & Cardinality**:
  - `farmer_profiles` (1) : (N) `farmer_crops`
  - `farmer_profiles` (1) : (N) `conversations`
  - `conversations` (1) : (N) `query_logs`
  - `query_logs` (1) : (1) `response_logs`
  - `source_documents` (1) : (N) `knowledge_chunks`

---

## Validation Performed

| Validation Criteria | Status | Evidence / Notes |
|---|:---:|---|
| **White Background & White Box Interiors** | **PASSED** | Canvas background is `#FFFFFF`, all boxes have `fill="#FFFFFF"`. |
| **Different Colored Box Outlines** | **PASSED** | Distinct strokes for green, blue, purple, teal, amber, red, and cyan subsystems. |
| **Different Colored Text** | **PASSED** | Titles and headers use subsystem-specific colors; body text uses high-contrast slate. |
| **Native Editable PowerPoint Slides** | **PASSED** | Generated `.pptx` presentations with native editable shapes, text boxes, and lines. |
| **System architecture matches code** | **PASSED** | Matches `advisor.py`, `retrieval.py`, `sarvam.py`, `grounding.py`. |
| **Workflow matches orchestration** | **PASSED** | Reflects S1–S10 pipeline implemented in `advisor.py` orchestration. |
| **ER diagram matches migrations** | **PASSED** | Matches all 10 tables, column data types, FKs, and relationships in migrations. |
| **All components actually implemented** | **PASSED** | Every component shown has corresponding backend code and migrations. |
| **Official data is source of truth** | **PASSED** | ICAR, SAUs, MoAFW, and Agmarknet/Data.gov.in clearly established as authoritative truth. |
| **Insufficient evidence / abstention shown** | **PASSED** | Explicit branches for abstention and refusal without LLM hallucination. |
| **Application and DB code untouched** | **PASSED** | Zero modifications made to backend, frontend, database, or application code. |
