import re
import unicodedata
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class PreprocessedQuery(BaseModel):
    request_id: str
    original_query: str
    normalized_query: str
    language: str
    timestamp: str
    farmer_context: Optional[Dict[str, Any]] = None


class QueryPreprocessor:
    """
    Safely normalizes farmer queries while preserving original regional text,
    accents, scripts (Devanagari, Telugu, Tamil, etc.), and metadata.
    """

    def process(
        self,
        query: str,
        language: str = "hi-IN",
        farmer_context: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ) -> PreprocessedQuery:
        if not query or not query.strip():
            raise ValueError("Query string cannot be empty")

        req_id = request_id or str(uuid.uuid4())
        original = query.strip()

        # Unicode NFKC normalization (recombines characters cleanly across scripts)
        normalized = unicodedata.normalize("NFKC", original)

        # Remove zero-width characters and unusual control codes without affecting native scripts
        normalized = re.sub(r"[\u200B-\u200D\uFEFF]", "", normalized)

        # Collapse excessive whitespace
        normalized = re.sub(r"\s+", " ", normalized).strip()

        now_utc = datetime.now(timezone.utc).isoformat()

        return PreprocessedQuery(
            request_id=req_id,
            original_query=original,
            normalized_query=normalized,
            language=language,
            timestamp=now_utc,
            farmer_context=farmer_context,
        )


query_preprocessor = QueryPreprocessor()
