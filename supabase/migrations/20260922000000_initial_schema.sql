-- ============================================================================
-- Supabase / PostgreSQL Initial Schema Migration
-- Migration: 20260922000000_initial_schema.sql
-- Description: Core tables for Farmer AI Advisory Assistant with pgvector
-- ============================================================================

-- Enable essential extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- pgvector extension for dense embedding vectors (768 dimensions for Gemini text-embedding-004)
-- Note: In Supabase, pgvector can be toggled in Database -> Extensions
CREATE EXTENSION IF NOT EXISTS "vector";

-- Trigger function to automatically maintain updated_at timestamps
CREATE OR REPLACE FUNCTION update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 1. FARMER PROFILES & CONTEXT
-- ============================================================================
CREATE TABLE IF NOT EXISTS farmer_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR(64) UNIQUE NOT NULL,      -- Anonymous client UUID or session token
    phone_number VARCHAR(15) UNIQUE,              -- Optional mobile number
    full_name VARCHAR(100),
    preferred_language VARCHAR(10) NOT NULL DEFAULT 'hi-IN', -- e.g. 'hi-IN', 'te-IN', 'ta-IN'
    state VARCHAR(50) NOT NULL,
    district VARCHAR(50) NOT NULL,
    sub_district VARCHAR(50),
    village VARCHAR(100),
    land_holding_acres NUMERIC(6, 2) DEFAULT 1.0,
    soil_type VARCHAR(50),                        -- e.g. 'Alluvial', 'Black', 'Red'
    irrigation_source VARCHAR(50),                -- e.g. 'Borewell', 'Canal', 'Rainfed'
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_farmer_session ON farmer_profiles(session_id);
CREATE INDEX IF NOT EXISTS idx_farmer_location ON farmer_profiles(state, district);

CREATE TRIGGER trg_farmer_profiles_updated_at
BEFORE UPDATE ON farmer_profiles
FOR EACH ROW EXECUTE FUNCTION update_timestamp();

-- Farmer crop context
CREATE TABLE IF NOT EXISTS farmer_crops (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    farmer_id UUID NOT NULL REFERENCES farmer_profiles(id) ON DELETE CASCADE,
    crop_name VARCHAR(50) NOT NULL,
    variety VARCHAR(50),
    sowing_date DATE,
    acreage NUMERIC(5, 2),
    stage VARCHAR(30),                            -- e.g. 'Sowing', 'Vegetative', 'Flowering', 'Harvesting'
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_farmer_crops_farmer ON farmer_crops(farmer_id);

CREATE TRIGGER trg_farmer_crops_updated_at
BEFORE UPDATE ON farmer_crops
FOR EACH ROW EXECUTE FUNCTION update_timestamp();

-- ============================================================================
-- 2. CONVERSATIONS, QUERIES & RESPONSES
-- ============================================================================
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    farmer_id UUID NOT NULL REFERENCES farmer_profiles(id) ON DELETE CASCADE,
    title VARCHAR(150),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversations_farmer ON conversations(farmer_id);

CREATE TRIGGER trg_conversations_updated_at
BEFORE UPDATE ON conversations
FOR EACH ROW EXECUTE FUNCTION update_timestamp();

CREATE TABLE IF NOT EXISTS query_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    farmer_id UUID NOT NULL REFERENCES farmer_profiles(id) ON DELETE CASCADE,
    input_channel VARCHAR(20) NOT NULL DEFAULT 'voice', -- 'voice' or 'text'
    audio_storage_path VARCHAR(255),
    detected_language VARCHAR(10) NOT NULL,
    raw_transcript TEXT NOT NULL,
    classified_intent VARCHAR(50) NOT NULL,             -- 'CROP_ADVISORY', 'PEST_DISEASE', 'MANDI_PRICE', 'GOVERNMENT_SCHEME'
    extracted_entities JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_query_logs_farmer ON query_logs(farmer_id);
CREATE INDEX IF NOT EXISTS idx_query_logs_intent ON query_logs(classified_intent);

CREATE TRIGGER trg_query_logs_updated_at
BEFORE UPDATE ON query_logs
FOR EACH ROW EXECUTE FUNCTION update_timestamp();

CREATE TABLE IF NOT EXISTS response_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_id UUID NOT NULL REFERENCES query_logs(id) ON DELETE CASCADE UNIQUE,
    response_text TEXT NOT NULL,
    audio_response_path VARCHAR(255),
    is_grounded BOOLEAN NOT NULL DEFAULT TRUE,
    confidence_score NUMERIC(4, 3),
    disclaimer_applied BOOLEAN NOT NULL DEFAULT FALSE,
    retrieved_sources JSONB DEFAULT '[]'::jsonb,
    latency_breakdown_ms JSONB DEFAULT '{}'::jsonb,
    farmer_feedback VARCHAR(20),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_response_logs_query ON response_logs(query_id);

CREATE TRIGGER trg_response_logs_updated_at
BEFORE UPDATE ON response_logs
FOR EACH ROW EXECUTE FUNCTION update_timestamp();

-- ============================================================================
-- 3. KNOWLEDGE BASE & SOURCE DOCUMENTS (RAG)
-- ============================================================================
CREATE TABLE IF NOT EXISTS source_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(255) NOT NULL,
    source_type VARCHAR(50) NOT NULL,                   -- 'ICAR', 'SAU_POP', 'KVK', 'CIBRC', 'GOV_PORTAL'
    issuing_authority VARCHAR(150) NOT NULL,            -- e.g., 'ICAR - Central Rice Research Institute'
    state_applicability VARCHAR(50) NOT NULL DEFAULT 'All-India',
    agro_climatic_zone VARCHAR(100),
    official_document_url VARCHAR(500),
    publication_year INT,
    version VARCHAR(30),
    verified_by_expert BOOLEAN NOT NULL DEFAULT TRUE,
    source_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_source_documents_updated_at
BEFORE UPDATE ON source_documents
FOR EACH ROW EXECUTE FUNCTION update_timestamp();

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES source_documents(id) ON DELETE CASCADE,
    -- Extensible metadata architecture: supports any crop, state, season, topic
    crop_name VARCHAR(100),
    state VARCHAR(50),
    language VARCHAR(10) NOT NULL DEFAULT 'en',
    season VARCHAR(30),                                 -- 'Kharif', 'Rabi', 'Zaid'
    growth_stage VARCHAR(50),                           -- 'Sowing', 'Vegetative', 'Flowering', 'Harvesting'
    topic VARCHAR(100),                                 -- 'Pest Management', 'Nutrient Management', 'Irrigation'
    content TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    token_count INT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    -- pgvector column for 768-dimensional embeddings
    embedding vector(768),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_doc ON knowledge_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_crop ON knowledge_chunks(crop_name);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_state ON knowledge_chunks(state);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_topic ON knowledge_chunks(topic);

-- HNSW vector similarity index for sub-10ms retrieval
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_embedding_hnsw 
ON knowledge_chunks 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

CREATE TRIGGER trg_knowledge_chunks_updated_at
BEFORE UPDATE ON knowledge_chunks
FOR EACH ROW EXECUTE FUNCTION update_timestamp();

-- ============================================================================
-- 4. GOVERNMENT AGRICULTURAL SCHEMES
-- ============================================================================
CREATE TABLE IF NOT EXISTS government_schemes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scheme_code VARCHAR(50) UNIQUE NOT NULL,            -- e.g., 'PM_KISAN', 'PMFBY', 'KCC'
    scheme_name VARCHAR(255) NOT NULL,
    name_translations JSONB DEFAULT '{}'::jsonb,
    short_description TEXT NOT NULL,
    benefits_summary TEXT NOT NULL,
    eligibility_criteria JSONB NOT NULL,
    required_documents JSONB NOT NULL,
    application_process TEXT NOT NULL,
    official_portal_url VARCHAR(500) NOT NULL,
    sponsoring_agency VARCHAR(100) NOT NULL,
    state_scope VARCHAR(50) NOT NULL DEFAULT 'Central',
    last_verified_date DATE NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gov_schemes_scope ON government_schemes(state_scope);
CREATE INDEX IF NOT EXISTS idx_gov_schemes_code ON government_schemes(scheme_code);

CREATE TRIGGER trg_government_schemes_updated_at
BEFORE UPDATE ON government_schemes
FOR EACH ROW EXECUTE FUNCTION update_timestamp();

-- ============================================================================
-- 5. MANDI / MARKET PRICE RECORDS (Agmarknet)
-- ============================================================================
CREATE TABLE IF NOT EXISTS mandi_prices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    state VARCHAR(50) NOT NULL,
    district VARCHAR(50) NOT NULL,
    market VARCHAR(100) NOT NULL,
    commodity VARCHAR(100) NOT NULL,
    variety VARCHAR(100) NOT NULL DEFAULT 'Common',
    grade VARCHAR(50) NOT NULL DEFAULT 'FAQ',
    arrival_date DATE NOT NULL,
    min_price NUMERIC(10, 2) NOT NULL,
    max_price NUMERIC(10, 2) NOT NULL,
    modal_price NUMERIC(10, 2) NOT NULL,
    source VARCHAR(100) NOT NULL DEFAULT 'Agmarknet / data.gov.in',
    -- Strict separation: 'production_live', 'production_cached', 'development_seed'
    data_origin VARCHAR(30) NOT NULL DEFAULT 'production_live',
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT unique_mandi_record UNIQUE (state, district, market, commodity, variety, arrival_date)
);

CREATE INDEX IF NOT EXISTS idx_mandi_lookup ON mandi_prices(commodity, state, district, arrival_date DESC);
CREATE INDEX IF NOT EXISTS idx_mandi_arrival_date ON mandi_prices(arrival_date DESC);

CREATE TRIGGER trg_mandi_prices_updated_at
BEFORE UPDATE ON mandi_prices
FOR EACH ROW EXECUTE FUNCTION update_timestamp();

-- ============================================================================
-- 6. DATA INGESTION & SYNC AUDIT LOGS
-- ============================================================================
CREATE TABLE IF NOT EXISTS sync_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sync_source VARCHAR(50) NOT NULL,                   -- 'AGMARKNET_DATA_GOV_IN', 'ICAR_POP_INGEST', 'MYSCHEME_SCRAPE'
    status VARCHAR(20) NOT NULL,                        -- 'SUCCESS', 'FAILED', 'PARTIAL'
    records_processed INT NOT NULL DEFAULT 0,
    records_inserted INT NOT NULL DEFAULT 0,
    records_updated INT NOT NULL DEFAULT 0,
    error_message TEXT,
    execution_time_seconds NUMERIC(8, 2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sync_logs_source ON sync_logs(sync_source, created_at DESC);

CREATE TRIGGER trg_sync_logs_updated_at
BEFORE UPDATE ON sync_logs
FOR EACH ROW EXECUTE FUNCTION update_timestamp();
