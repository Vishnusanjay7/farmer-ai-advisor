import pytest
from backend.app.db.session import SessionLocal
from backend.app.models.models import SourceDocument, KnowledgeChunk, SyncLog
from scripts.ingest_agricultural_knowledge import run_ingestion_pipeline


@pytest.mark.asyncio
async def test_knowledge_ingestion_and_deduplication():
    db = SessionLocal()

    # Run ingestion
    await run_ingestion_pipeline()
    initial_doc_count = db.query(SourceDocument).count()
    initial_chunk_count = db.query(KnowledgeChunk).count()

    assert initial_doc_count >= 6
    assert initial_chunk_count >= 20

    # Run ingestion a second time to verify deduplication
    await run_ingestion_pipeline()
    second_doc_count = db.query(SourceDocument).count()
    second_chunk_count = db.query(KnowledgeChunk).count()

    # Counts must NOT double
    assert second_doc_count == initial_doc_count
    assert second_chunk_count == initial_chunk_count

    # Verify audit logs
    sync_logs = db.query(SyncLog).filter(SyncLog.sync_source == "ICAR_POP_INGEST").all()
    assert len(sync_logs) >= 2
    for log in sync_logs:
        assert log.status == "SUCCESS"
        assert log.records_processed >= 6
        assert log.execution_time_seconds is not None
        # Ensure no secrets in error messages
        assert log.error_message is None

    db.close()
