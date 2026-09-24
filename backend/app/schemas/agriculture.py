from typing import List, Optional, Dict, Any
from pydantic import BaseModel


class SourceDocumentResponse(BaseModel):
    id: str
    title: str
    source_name: Optional[str] = None
    source_type: str
    issuing_authority: str
    state_applicability: str
    agro_climatic_zone: Optional[str] = None
    official_document_url: Optional[str] = None
    publication_year: Optional[int] = None
    version: Optional[str] = None
    verified_by_expert: bool
    source_date: Optional[str] = None
    language: str
    total_chunks: int = 0


class AgricultureSourcesResponse(BaseModel):
    total: int
    page: int
    page_size: int
    sources: List[SourceDocumentResponse]


class TopicCountItem(BaseModel):
    topic: str
    crop_name: Optional[str] = None
    chunk_count: int


class AgricultureTopicsResponse(BaseModel):
    total_topics: int
    topics: List[TopicCountItem]
