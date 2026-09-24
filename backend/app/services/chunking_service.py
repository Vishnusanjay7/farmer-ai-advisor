import hashlib
import re
from typing import List, Dict, Any, Optional
from pydantic import BaseModel


class DocumentChunk(BaseModel):
    chunk_index: int
    content: str
    content_hash: str
    token_count: int
    topic: Optional[str] = None
    crop_name: Optional[str] = None
    growth_stage: Optional[str] = None
    season: Optional[str] = None
    state: Optional[str] = None
    metadata: Dict[str, Any] = {}


class AgronomicChunker:
    """
    Deterministic chunking service that preserves paragraph and section boundaries,
    retains agronomic context (headers, crop, pest names), and calculates deterministic SHA-256 hashes.
    """

    def __init__(self, max_tokens: int = 450, overlap_tokens: int = 50):
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens

    def estimate_tokens(self, text: str) -> int:
        """Approximates token count (avg ~1.3 tokens per whitespace-separated word)."""
        words = len(text.split())
        return int(words * 1.3)

    def chunk_document(
        self,
        document_text: str,
        base_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[DocumentChunk]:
        base_meta = base_metadata or {}
        chunks: List[DocumentChunk] = []

        # Split on markdown headings or double newlines to respect section boundaries
        sections = re.split(r"\n(?=#{1,4}\s+)", document_text.strip())
        chunk_idx = 0
        seen_hashes = set()

        for section in sections:
            section_clean = section.strip()
            if not section_clean:
                continue

            # Extract section heading if present
            heading_match = re.match(r"^(#{1,4})\s+(.+)$", section_clean, re.MULTILINE)
            section_heading = heading_match.group(2).strip() if heading_match else None

            # If section fits within max_tokens, keep as single cohesive chunk
            section_tokens = self.estimate_tokens(section_clean)
            if section_tokens <= self.max_tokens:
                sub_chunks = [section_clean]
            else:
                # Subdivide by paragraphs
                paragraphs = re.split(r"\n\s*\n", section_clean)
                current_chunk = []
                current_count = 0
                sub_chunks = []

                for para in paragraphs:
                    para = para.strip()
                    if not para:
                        continue
                    p_tokens = self.estimate_tokens(para)
                    if current_count + p_tokens > self.max_tokens and current_chunk:
                        sub_chunks.append("\n\n".join(current_chunk))
                        current_chunk = [para]
                        current_count = p_tokens
                    else:
                        current_chunk.append(para)
                        current_count += p_tokens

                if current_chunk:
                    sub_chunks.append("\n\n".join(current_chunk))

            for text_chunk in sub_chunks:
                text_chunk = text_chunk.strip()
                if not text_chunk:
                    continue

                # Prepend section heading context if chunk is a broken sub-part
                if section_heading and not text_chunk.startswith("#"):
                    annotated_content = f"[{section_heading}]\n{text_chunk}"
                else:
                    annotated_content = text_chunk

                # Compute deterministic content hash
                content_hash = hashlib.sha256(annotated_content.encode("utf-8")).hexdigest()
                if content_hash in seen_hashes:
                    continue  # Deduplicate identical chunks
                seen_hashes.add(content_hash)

                token_cnt = self.estimate_tokens(annotated_content)
                meta = dict(base_meta)
                if section_heading:
                    meta["section_heading"] = section_heading

                raw_topic = base_meta.get("topic") or (section_heading if section_heading else "General")
                topic_str = raw_topic[:100] if raw_topic else "General"

                chunks.append(
                    DocumentChunk(
                        chunk_index=chunk_idx,
                        content=annotated_content,
                        content_hash=content_hash,
                        token_count=token_cnt,
                        topic=topic_str,
                        crop_name=base_meta.get("crop_name"),
                        growth_stage=base_meta.get("growth_stage"),
                        season=base_meta.get("season"),
                        state=base_meta.get("state", "All-India"),
                        metadata=meta,
                    )
                )
                chunk_idx += 1

        return chunks
