import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Load .env.staging
staging_env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env.staging"))
if os.path.exists(staging_env_path):
    from dotenv import load_dotenv
    load_dotenv(staging_env_path)

from backend.app.core.config import settings
from sqlalchemy import create_engine, text

def run_database_audit():
    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as conn:
        print("=== ALL 10 TABLE ROW COUNTS ===")
        tables = [
            'source_documents', 'knowledge_chunks', 'government_schemes',
            'mandi_prices', 'sync_logs', 'farmer_profiles', 'farmer_crops',
            'conversations', 'query_logs', 'response_logs'
        ]
        for t in tables:
            count = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            print(f"  - {t}: {count}")

        print("\n=== EMBEDDING AUDIT ===")
        total_chunks = conn.execute(text("SELECT COUNT(*) FROM knowledge_chunks")).scalar()
        null_embeddings = conn.execute(text("SELECT COUNT(*) FROM knowledge_chunks WHERE embedding IS NULL")).scalar()
        dims = conn.execute(text("SELECT DISTINCT vector_dims(embedding) FROM knowledge_chunks")).fetchall()
        print(f"  - Total chunks: {total_chunks}")
        print(f"  - Chunks with embedding: {total_chunks - null_embeddings}/{total_chunks}")
        print(f"  - Embedding dimensions: {[d[0] for d in dims]}")

        print("\n=== HASH & INDEX AUDIT ===")
        dup_kc_hashes = conn.execute(text("SELECT content_hash, COUNT(*) FROM knowledge_chunks GROUP BY content_hash HAVING COUNT(*) > 1")).fetchall()
        dup_sd_hashes = conn.execute(text("SELECT content_hash, COUNT(*) FROM source_documents GROUP BY content_hash HAVING COUNT(*) > 1")).fetchall()
        print(f"  - Duplicate chunk content_hash: {len(dup_kc_hashes)}")
        print(f"  - Duplicate source content_hash: {len(dup_sd_hashes)}")

        print("\n=== PROVENANCE AUDIT ===")
        prov_check = conn.execute(text("SELECT COUNT(*) FROM source_documents WHERE source_name IS NULL OR issuing_authority IS NULL OR official_document_url IS NULL OR content_hash IS NULL")).scalar()
        print(f"  - Incomplete source provenance rows: {prov_check}")

        print("\n=== CHUNK ORDERING AUDIT ===")
        order_check = conn.execute(text("SELECT document_id, MIN(chunk_index), MAX(chunk_index), COUNT(chunk_index) FROM knowledge_chunks GROUP BY document_id")).fetchall()
        valid_order = all(min_i == 0 and max_i == count - 1 for _, min_i, max_i, count in order_check)
        print(f"  - Chunk index ordering contiguous & zero-indexed: {valid_order}")

        print("\n=== EXTENSION & INDEX AUDIT ===")
        ext = conn.execute(text("SELECT extname, extversion FROM pg_extension WHERE extname='vector'")).fetchone()
        print(f"  - Extension: {ext[0]} v{ext[1]}")
        idx = conn.execute(text("SELECT indexname, indexdef FROM pg_indexes WHERE tablename='knowledge_chunks' AND indexname='idx_knowledge_chunks_embedding_hnsw'")).fetchone()
        print(f"  - HNSW Index: {idx[0]}")
        print(f"  - Definition: {idx[1]}")

        print("\n=== DATA ORIGIN SAFETY ===")
        dev_seed_count = conn.execute(text("SELECT COUNT(*) FROM mandi_prices WHERE data_origin='development_seed'")).scalar()
        print(f"  - mandi_prices development_seed rows: {dev_seed_count}")

    engine.dispose()

if __name__ == "__main__":
    run_database_audit()
