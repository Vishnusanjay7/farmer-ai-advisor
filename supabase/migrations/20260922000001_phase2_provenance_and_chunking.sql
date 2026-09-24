-- ============================================================================
-- Supabase / PostgreSQL Migration: Phase 2 Data Provenance & Chunk Ordering
-- Migration: 20260922000001_phase2_provenance_and_chunking.sql
-- Description: Enhances source_documents with content_hash, language, and provenance
--              metadata, and adds chunk_index to knowledge_chunks for ordering.
-- ============================================================================

-- 1. Enhance source_documents with provenance and deduplication hash
ALTER TABLE source_documents
ADD COLUMN IF NOT EXISTS source_name VARCHAR(150),
ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64) UNIQUE,
ADD COLUMN IF NOT EXISTS fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
ADD COLUMN IF NOT EXISTS language VARCHAR(10) NOT NULL DEFAULT 'en',
ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_source_documents_hash ON source_documents(content_hash);
CREATE INDEX IF NOT EXISTS idx_source_documents_authority ON source_documents(issuing_authority);

-- 2. Enhance knowledge_chunks with chunk_index to preserve section/document order
ALTER TABLE knowledge_chunks
ADD COLUMN IF NOT EXISTS chunk_index INT NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_order ON knowledge_chunks(document_id, chunk_index);
