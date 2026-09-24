import hashlib
import math
from typing import List, Optional
import httpx

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.providers.base import EmbeddingProvider


class GeminiEmbeddingProvider(EmbeddingProvider):
    """
    Produces 768-dimensional dense vector embeddings using Google Gemini models (e.g. gemini-embedding-001).
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.GEMINI_API_KEY or settings.LLM_API_KEY
        self.model = model or getattr(settings, "EMBEDDING_MODEL", "gemini-embedding-001")
        self.expected_dimension = settings.EMBEDDING_DIMENSION  # 768

    async def generate_embedding(self, text: str) -> List[float]:
        if not self.api_key:
            raise ValueError(
                "GeminiEmbeddingProvider requires GEMINI_API_KEY or LLM_API_KEY in environment variables."
            )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:embedContent?key={self.api_key}"
        payload = {
            "model": f"models/{self.model}",
            "content": {"parts": [{"text": text}]},
            "outputDimensionality": self.expected_dimension,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=payload)
            if response.status_code != 200:
                raise RuntimeError(
                    f"Gemini embedding API failed with HTTP {response.status_code}: {response.text}"
                )
            data = response.json()
            embedding_values = data.get("embedding", {}).get("values", [])

        # Strict dimension verification
        if len(embedding_values) != self.expected_dimension:
            raise ValueError(
                f"Embedding dimension mismatch! Database expects {self.expected_dimension}, "
                f"but {self.model} returned {len(embedding_values)}. Do not truncate or pad."
            )

        return embedding_values


class DeterministicMockEmbeddingProvider(EmbeddingProvider):
    """
    Generates deterministic, unit-normalized 768-dimensional embeddings from text hashes.
    Strictly for testing and development environments where external API credentials are not provided.
    Never used in live production data claims.
    """

    def __init__(self, dimension: int = 768):
        self.dimension = dimension

    async def generate_embedding(self, text: str) -> List[float]:
        return self._generate_vector_pure(text)

    def generate_embedding_sync(self, text: str) -> List[float]:
        """Synchronous version for test seeding and migration scripts."""
        return self._generate_vector_pure(text)

    def _generate_vector_pure(self, text: str) -> List[float]:
        vector = []
        salt = 0
        while len(vector) < self.dimension:
            h = hashlib.sha512(f"{salt}:{text}".encode("utf-8")).digest()
            for i in range(0, len(h) - 1, 2):
                val = (int.from_bytes(h[i : i + 2], "big") / 32767.5) - 1.0
                vector.append(val)
                if len(vector) == self.dimension:
                    break
            salt += 1
        norm = math.sqrt(sum(x * x for x in vector))
        if norm > 0:
            vector = [x / norm for x in vector]
        return vector


def get_embedding_provider() -> EmbeddingProvider:
    """Factory returning configured embedding provider."""
    provider_type = getattr(settings, "EMBEDDING_PROVIDER", "gemini").lower()
    has_gemini_key = bool(settings.GEMINI_API_KEY or settings.LLM_API_KEY)

    if settings.ENVIRONMENT in ("production", "staging"):
        if provider_type == "gemini" and not has_gemini_key:
            raise ValueError(
                f"GEMINI_API_KEY is required in {settings.ENVIRONMENT} mode for vector embeddings. "
                "Silent fallback to mock embeddings is strictly prohibited."
            )
        if provider_type != "gemini":
            raise ValueError(
                f"Unsupported EMBEDDING_PROVIDER '{provider_type}' in {settings.ENVIRONMENT} mode. "
                "Production and staging require a verified live embedding provider."
            )

    if provider_type == "gemini" and has_gemini_key:
        logger.info(f"Initializing GeminiEmbeddingProvider with model={settings.EMBEDDING_MODEL} (768-dim)")
        return GeminiEmbeddingProvider(model=settings.EMBEDDING_MODEL)
    else:
        logger.warning(
            "Using DeterministicMockEmbeddingProvider (768-dim) for development/testing."
        )
        return DeterministicMockEmbeddingProvider(dimension=settings.EMBEDDING_DIMENSION)
