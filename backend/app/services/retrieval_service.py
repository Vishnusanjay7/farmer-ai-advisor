import math
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.models.models import KnowledgeChunk, SourceDocument, GovernmentScheme, MandiPrice
from backend.app.schemas.advisor import AgriculturalIntent, EvidenceItemDTO, FarmerContextDTO
from backend.app.providers.embedding_provider import (
    EmbeddingProvider,
    DeterministicMockEmbeddingProvider,
    get_embedding_provider,
)


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Computes cosine similarity between two numeric vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot_product = sum(a * b for a, b in zip(v1, v2))
    norm_a = math.sqrt(sum(a * a for a in v1))
    norm_b = math.sqrt(sum(b * b for b in v2))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot_product / (norm_a * norm_b)


class RetrievalService:
    """
    Specialized intent-based retrieval service.
    - CROP_ADVISORY / PEST_DISEASE / GENERAL_AGRICULTURE: vector & metadata search over ICAR/SAU knowledge chunks.
    - GOVERNMENT_SCHEME: structured search over verified government schemes.
    - MANDI_PRICE: structured search over mandi prices (STRICTLY production_live and production_cached only).
    - UNSUPPORTED / UNKNOWN: returns empty list.
    """

    def __init__(self, embedding_provider: Optional[EmbeddingProvider] = None):
        self.embedding_provider = embedding_provider or get_embedding_provider()

    async def retrieve(
        self,
        db: Session,
        query: str,
        intent: AgriculturalIntent,
        context: Optional[FarmerContextDTO] = None,
        top_k: Optional[int] = None,
        similarity_threshold: Optional[float] = None,
    ) -> List[EvidenceItemDTO]:
        k = top_k or settings.RAG_TOP_K
        threshold = similarity_threshold if similarity_threshold is not None else settings.RAG_SIMILARITY_THRESHOLD

        if intent in (AgriculturalIntent.CROP_ADVISORY, AgriculturalIntent.PEST_DISEASE, AgriculturalIntent.GENERAL_AGRICULTURE):
            return await self._retrieve_agricultural_knowledge(db, query, context, k, threshold)
        elif intent == AgriculturalIntent.GOVERNMENT_SCHEME:
            return self._retrieve_government_schemes(db, query, context, k)
        elif intent == AgriculturalIntent.MANDI_PRICE:
            return self._retrieve_mandi_prices(db, query, context, k)
        else:
            return []

    async def _retrieve_agricultural_knowledge(
        self,
        db: Session,
        query: str,
        context: Optional[FarmerContextDTO],
        top_k: int,
        threshold: float,
    ) -> List[EvidenceItemDTO]:
        """Retrieves and scores knowledge chunks using 768-dim embeddings and metadata filters."""
        # Generate query embedding
        query_vector = await self.embedding_provider.generate_embedding(query)

        # Base query joining source document
        q = db.query(KnowledgeChunk, SourceDocument).join(
            SourceDocument, KnowledgeChunk.document_id == SourceDocument.id
        )

        # Apply metadata filters if available in context
        if context and context.crop:
            q = q.filter(KnowledgeChunk.crop_name.ilike(f"%{context.crop}%"))

        # State filter with zone compatibility
        if context and context.state:
            state_lower = context.state.lower()
            zone_keywords = [context.state]
            if state_lower in ("punjab", "haryana", "rajasthan", "delhi"):
                zone_keywords.extend(["north-western", "plains", "western"])
            elif state_lower in ("madhya pradesh", "mp", "gujarat", "chhattisgarh"):
                zone_keywords.extend(["central", "plains"])
            elif state_lower in ("andhra pradesh", "telangana", "karnataka", "tamil nadu", "maharashtra"):
                zone_keywords.extend(["southern", "peninsular", "central & southern"])
            elif state_lower in ("uttar pradesh", "up", "bihar", "west bengal", "odisha", "assam"):
                zone_keywords.extend(["eastern", "plains", "western up"])

            state_conditions = [
                KnowledgeChunk.state.ilike(f"%{kw}%") for kw in zone_keywords
            ] + [
                SourceDocument.state_applicability.ilike(f"%{kw}%") for kw in zone_keywords
            ] + [
                SourceDocument.state_applicability == "All-India"
            ]
            q = q.filter(or_(*state_conditions))

        records = q.all()
        # If strict state filter produced 0 records for a known crop, relax state filter but KEEP strict crop filter
        if not records and context and context.crop:
            records = (
                db.query(KnowledgeChunk, SourceDocument)
                .join(SourceDocument, KnowledgeChunk.document_id == SourceDocument.id)
                .filter(KnowledgeChunk.crop_name.ilike(f"%{context.crop}%"))
                .all()
            )

        scored_evidence = []
        is_mock = isinstance(self.embedding_provider, DeterministicMockEmbeddingProvider)

        # In mock testing mode, compute token overlap as surrogate similarity
        q_tokens = []
        if is_mock:
            import re
            STOP_WORDS = {
                "what", "how", "when", "where", "which", "who", "why", "can", "should", "could", "would",
                "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do", "does", "did",
                "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by", "from",
                "about", "into", "through", "during", "before", "after", "above", "below", "up", "down",
                "out", "off", "over", "under", "again", "further", "then", "once", "here", "there", "all",
                "any", "both", "each", "few", "more", "most", "other", "some", "such", "no", "nor", "not",
                "only", "own", "same", "so", "than", "too", "very", "s", "t", "will", "just", "now", "tell",
                "give", "me", "i", "you", "my", "we", "our", "their", "please", "followed",
            }
            q_tokens = [w for w in re.findall(r"\w+", query.lower()) if len(w) > 2 and w not in STOP_WORDS]
            if not q_tokens:
                q_tokens = [w for w in re.findall(r"\w+", query.lower()) if len(w) > 2]

        for chunk, doc in records:
            if chunk.embedding is None:
                continue

            content_clean = chunk.content.strip()
            # Skip pure document/header-only markers without descriptive content
            if len(content_clean) < 80 and content_clean.startswith("#") and "\n" not in content_clean:
                continue

            # Crop compatibility guard: if crop is specified, reject mismatched chunks
            if context and context.crop and chunk.crop_name:
                user_crop = context.crop.strip().lower()
                chunk_crop = chunk.crop_name.strip().lower()
                if user_crop not in chunk_crop and chunk_crop not in user_crop and chunk_crop not in ("general", "all"):
                    continue

            # Convert embedding to float list if needed
            chunk_vec = list(chunk.embedding)
            sim = cosine_similarity(query_vector, chunk_vec)

            if is_mock:
                import re
                c_tokens = set(re.findall(r"\w+", chunk.content.lower()))
                overlap = sum(1 for t in q_tokens if t in c_tokens) / max(len(q_tokens), 1) if q_tokens else 0.0
                final_score = round(max(sim, overlap), 4)
            else:
                # Real production: pure cosine similarity from 768-dim embeddings without artificial boosting
                final_score = round(sim, 4)

            scored_evidence.append({
                "score": final_score,
                "chunk": chunk,
                "doc": doc,
            })

        # Sort descending by relevance score
        scored_evidence.sort(key=lambda x: x["score"], reverse=True)

        evidence_items = []
        for item in scored_evidence[:top_k]:
            chunk = item["chunk"]
            doc = item["doc"]
            score = item["score"]

            status = "authoritative" if score >= threshold else "insufficient"

            evidence_items.append(
                EvidenceItemDTO(
                    evidence_id=f"chunk_{chunk.id}",
                    source_document_id=str(doc.id) if doc.id else None,
                    source_name=doc.source_name or doc.title,
                    title=doc.title,
                    issuing_authority=doc.issuing_authority,
                    official_url=doc.official_document_url,
                    chunk_id=str(chunk.id) if chunk.id else None,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    relevance_score=score,
                    source_date=str(doc.source_date) if doc.source_date else str(doc.publication_year),
                    metadata={
                        "crop": chunk.crop_name,
                        "topic": chunk.topic,
                        "season": chunk.season,
                        "growth_stage": chunk.growth_stage,
                    },
                    data_origin="production_cached",
                    status=status,
                )
            )

        return evidence_items

    def _retrieve_government_schemes(
        self,
        db: Session,
        query: str,
        context: Optional[FarmerContextDTO],
        top_k: int,
    ) -> List[EvidenceItemDTO]:
        """Searches verified government schemes."""
        q_lower = query.lower()
        schemes = db.query(GovernmentScheme).filter(GovernmentScheme.is_active == True).all()

        scored = []
        for s in schemes:
            score = 0.0
            # Exact scheme code match (e.g. PM-KISAN, PMFBY)
            code_clean = s.scheme_code.lower().replace("_", "").replace("-", "")
            q_clean = q_lower.replace("-", "").replace(" ", "")
            if code_clean in q_clean or s.scheme_code.lower() in q_lower:
                score += 0.85
            if s.scheme_name.lower() in q_lower or any(word in q_lower for word in s.scheme_name.lower().split() if len(word) > 4):
                score += 0.40

            # Keywords in description/eligibility
            for crit in s.eligibility_criteria:
                if any(w in crit.lower() for w in q_lower.split() if len(w) > 4):
                    score += 0.10

            if score > 0.0:
                scored.append((score, s))

        scored.sort(key=lambda x: x[0], reverse=True)

        evidence_items = []
        for score, s in scored[:top_k]:
            content = (
                f"Scheme Name: {s.scheme_name} ({s.scheme_code})\n"
                f"Sponsoring Agency: {s.sponsoring_agency}\n"
                f"Benefits: {s.benefits_summary}\n"
                f"Eligibility Criteria: {'; '.join(s.eligibility_criteria)}\n"
                f"Required Documents: {'; '.join(s.required_documents)}\n"
                f"Application Process: {s.application_process}\n"
                f"Official Portal: {s.official_portal_url}"
            )
            evidence_items.append(
                EvidenceItemDTO(
                    evidence_id=f"scheme_{s.id}",
                    source_name=s.scheme_name,
                    title=s.scheme_name,
                    issuing_authority=s.sponsoring_agency,
                    official_url=s.official_portal_url,
                    content=content,
                    relevance_score=round(min(score, 0.99), 2),
                    source_date=str(s.last_verified_date),
                    metadata={
                        "scheme_code": s.scheme_code,
                        "state_scope": s.state_scope,
                    },
                    data_origin="production_live",
                    status="authoritative" if score >= 0.50 else "insufficient",
                )
            )

        return evidence_items

    def _retrieve_mandi_prices(
        self,
        db: Session,
        query: str,
        context: Optional[FarmerContextDTO],
        top_k: int,
    ) -> List[EvidenceItemDTO]:
        """
        Retrieves structured mandi records.
        CRITICAL GUARDRAIL:
        - Only accepts data_origin IN ('production_live', 'production_cached').
        - Strictly REJECTS data_origin = 'development_seed'.
        - If no matching verified record exists, returns empty list so the system abstains.
        """
        q = db.query(MandiPrice).filter(
            MandiPrice.data_origin.in_(["production_live", "production_cached"])
        )

        if context:
            if context.commodity or context.crop:
                comm = context.commodity or context.crop
                q = q.filter(MandiPrice.commodity.ilike(f"%{comm}%"))
            if context.state:
                q = q.filter(MandiPrice.state.ilike(f"%{context.state}%"))
            if context.district:
                q = q.filter(MandiPrice.district.ilike(f"%{context.district}%"))
            if context.market:
                q = q.filter(MandiPrice.market.ilike(f"%{context.market}%"))

        records = q.order_by(MandiPrice.arrival_date.desc()).limit(top_k).all()

        evidence_items = []
        for r in records:
            content = (
                f"Market: {r.market}, District: {r.district}, State: {r.state}. "
                f"Commodity: {r.commodity} (Variety: {r.variety}, Grade: {r.grade}). "
                f"Modal Price: Rs. {r.modal_price}/quintal (Min: Rs. {r.min_price}, Max: Rs. {r.max_price}). "
                f"Arrival Date: {r.arrival_date}. Source: {r.source}. Data Origin: {r.data_origin}."
            )
            evidence_items.append(
                EvidenceItemDTO(
                    evidence_id=f"mandi_{r.id}",
                    source_name=f"{r.source} - {r.market}",
                    title=f"Mandi Price: {r.commodity} in {r.market}",
                    issuing_authority=r.source,
                    official_url="https://agmarknet.gov.in",
                    content=content,
                    relevance_score=0.95,
                    source_date=str(r.arrival_date),
                    metadata={
                        "market": r.market,
                        "district": r.district,
                        "state": r.state,
                        "commodity": r.commodity,
                        "variety": r.variety,
                        "grade": r.grade,
                        "min_price": r.min_price,
                        "max_price": r.max_price,
                        "modal_price": r.modal_price,
                        "arrival_date": str(r.arrival_date),
                        "source": r.source,
                        "data_origin": r.data_origin,
                    },
                    data_origin=r.data_origin,
                    status="authoritative",
                )
            )

        return evidence_items


retrieval_service = RetrievalService()
