from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.app.db.session import get_db
from backend.app.models.models import SourceDocument, KnowledgeChunk
from backend.app.schemas.agriculture import (
    AgricultureSourcesResponse,
    SourceDocumentResponse,
    AgricultureTopicsResponse,
    TopicCountItem,
)

router = APIRouter(prefix="/agriculture", tags=["Agricultural Knowledge Provenance"])


@router.get("/sources", response_model=AgricultureSourcesResponse)
async def get_agriculture_sources(
    source_type: Optional[str] = Query(None, description="Filter by authority type (e.g. 'ICAR', 'SAU_POP', 'KVK')"),
    state: Optional[str] = Query(None, description="State applicability filter"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> AgricultureSourcesResponse:
    """
    Returns verified authoritative agricultural source documents with full provenance,
    issuing authorities, publication dates, and chunk counts.
    """
    query = db.query(SourceDocument)

    if source_type:
        query = query.filter(SourceDocument.source_type == source_type.upper())
    if state and state.lower() != "all":
        query = query.filter(SourceDocument.state_applicability.ilike(f"%{state}%"))

    total = query.count()
    offset = (page - 1) * page_size
    docs = query.order_by(SourceDocument.title.asc()).offset(offset).limit(page_size).all()

    items = []
    for d in docs:
        chunk_count = db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == d.id).count()
        items.append(
            SourceDocumentResponse(
                id=str(d.id),
                title=d.title,
                source_name=d.source_name,
                source_type=d.source_type,
                issuing_authority=d.issuing_authority,
                state_applicability=d.state_applicability,
                agro_climatic_zone=d.agro_climatic_zone,
                official_document_url=d.official_document_url,
                publication_year=d.publication_year,
                version=d.version,
                verified_by_expert=d.verified_by_expert,
                source_date=d.source_date.isoformat() if d.source_date else None,
                language=d.language,
                total_chunks=chunk_count,
            )
        )

    return AgricultureSourcesResponse(
        total=total,
        page=page,
        page_size=page_size,
        sources=items,
    )


@router.get("/topics", response_model=AgricultureTopicsResponse)
async def get_agriculture_topics(
    crop: Optional[str] = Query(None, description="Filter topics by crop name"),
    db: Session = Depends(get_db),
) -> AgricultureTopicsResponse:
    """
    Returns available verified agronomic topics and chunk coverage in the knowledge store.
    """
    query = db.query(
        KnowledgeChunk.topic,
        KnowledgeChunk.crop_name,
        func.count(KnowledgeChunk.id).label("chunk_count"),
    ).filter(KnowledgeChunk.topic.isnot(None))

    if crop:
        query = query.filter(KnowledgeChunk.crop_name.ilike(f"%{crop}%"))

    results = (
        query.group_by(KnowledgeChunk.topic, KnowledgeChunk.crop_name)
        .order_by(func.count(KnowledgeChunk.id).desc())
        .all()
    )

    topic_items = [
        TopicCountItem(
            topic=r[0] or "General",
            crop_name=r[1],
            chunk_count=r[2],
        )
        for r in results
    ]

    return AgricultureTopicsResponse(
        total_topics=len(topic_items),
        topics=topic_items,
    )
