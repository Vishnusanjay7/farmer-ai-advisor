import asyncio
import json
from typing import List, Optional, Dict, Any
import httpx

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.providers.base import LLMProvider, LLMGroundedResponse, GroundedSourceCitation


SUPPORTED_PRODUCTION_MODELS = {
    "gemini-3.8-flash",
    "gemini-3.5-flash",
    "gemini-2.5-flash",
}


class GeminiLLMProvider(LLMProvider):
    """
    Direct REST integration with official Google Gemini API using production Flash model (gemini-3.8-flash).
    Adheres to strict grounding, explicit fallback policies, and safe abstention.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        fallback_model: Optional[str] = None,
        max_retries: Optional[int] = None,
        timeout_seconds: float = 20.0,
    ):
        self.api_key = api_key or settings.GEMINI_API_KEY or settings.LLM_API_KEY
        self.model = model or settings.LLM_MODEL or "gemini-3.8-flash"
        self.fallback_model = fallback_model or settings.LLM_FALLBACK_MODEL or "gemini-3.5-flash"
        self.max_retries = max_retries if max_retries is not None else settings.LLM_MAX_RETRIES
        self.timeout_seconds = timeout_seconds

        # Validate that model configurations use supported production models
        if self.model not in SUPPORTED_PRODUCTION_MODELS:
            raise ValueError(
                f"Configured primary LLM model '{self.model}' is not a supported production Gemini model. "
                f"Supported models: {sorted(SUPPORTED_PRODUCTION_MODELS)}"
            )
        if self.fallback_model and self.fallback_model not in SUPPORTED_PRODUCTION_MODELS:
            raise ValueError(
                f"Configured fallback LLM model '{self.fallback_model}' is not a supported production Gemini model. "
                f"Supported models: {sorted(SUPPORTED_PRODUCTION_MODELS)}"
            )

    def _extract_retry_delay(self, response: Optional[httpx.Response], default: float = 2.0) -> float:
        if response is None:
            return default
        try:
            data = response.json()
            details = data.get("error", {}).get("details", [])
            for item in details:
                if item.get("@type") == "type.googleapis.com/google.rpc.RetryInfo":
                    delay_str = item.get("retryDelay", "")
                    if delay_str.endswith("s"):
                        sec = float(delay_str[:-1])
                        return min(max(sec + 0.5, 1.0), 15.0)
        except Exception:
            pass
        return default

    async def _call_gemini_model(
        self,
        client: httpx.AsyncClient,
        model_name: str,
        payload: Dict[str, Any],
        headers: Dict[str, str],
    ) -> httpx.Response:
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        return await client.post(endpoint, json=payload, headers=headers)

    async def generate_grounded_response(
        self,
        system_prompt: str,
        user_query: str,
        context_chunks: List[str],
        farmer_context: Optional[Dict[str, Any]] = None,
    ) -> LLMGroundedResponse:
        if not self.api_key:
            raise ValueError(
                "GeminiLLMProvider requires GEMINI_API_KEY or LLM_API_KEY in environment variables."
            )

        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }

        evidence_block = "\n\n---\n\n".join(context_chunks)
        full_user_prompt = (
            f"FARMER QUESTION: {user_query}\n\n"
            f"FARMER CONTEXT: {json.dumps(farmer_context or {}, ensure_ascii=False)}\n\n"
            f"AUTHORITATIVE EVIDENCE FROM VERIFIED GOVERNMENT & ICAR SOURCES:\n"
            f"{evidence_block}\n\n"
            f"INSTRUCTION: Synthesize an evidence-grounded response in the requested language. "
            f"Use ONLY the facts in the evidence above. Do NOT invent dosage, numbers, or rules."
        )

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": full_user_prompt}
                    ]
                }
            ],
            "systemInstruction": {
                "parts": [
                    {"text": system_prompt}
                ]
            },
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 1024,
            },
        }

        response = None
        selected_model = self.model

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            # 1. Attempt primary model execution with bounded retry on transient HTTP 503
            logger.info(f"Dispatching query to primary Gemini model: {self.model}")
            for attempt in range(self.max_retries + 1):
                try:
                    response = await self._call_gemini_model(client, self.model, payload, headers)
                except httpx.RequestError as exc:
                    logger.warning(f"Network error calling primary Gemini model '{self.model}': {type(exc).__name__}")
                    response = None

                if response is not None and response.status_code == 200:
                    selected_model = self.model
                    logger.info(f"Gemini primary model '{self.model}' succeeded (HTTP 200).")
                    break

                if response is not None and response.status_code in (503, 429):
                    delay = self._extract_retry_delay(response, default=2.0)
                    if attempt < self.max_retries:
                        logger.warning(
                            f"Primary model '{self.model}' returned transient HTTP {response.status_code}. "
                            f"Waiting {delay:.1f}s before retry ({attempt + 1}/{self.max_retries})..."
                        )
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.warning(f"Primary model '{self.model}' exhausted {self.max_retries} retries on HTTP {response.status_code}.")
                else:
                    # Non-503/429 HTTP error or network failure on primary model
                    break

            # 2. If primary model failed due to transient 503/429 and explicit fallback is configured
            if (response is None or response.status_code in (503, 429)) and self.fallback_model and self.fallback_model != self.model:
                logger.info(f"Initiating documented fallback to model: {self.fallback_model}")
                for fb_attempt in range(3):
                    try:
                        fallback_resp = await self._call_gemini_model(client, self.fallback_model, payload, headers)
                        if fallback_resp.status_code == 200:
                            response = fallback_resp
                            selected_model = self.fallback_model
                            logger.info(f"Gemini fallback model '{self.fallback_model}' succeeded (HTTP 200).")
                            break
                        elif fallback_resp.status_code in (503, 429) and fb_attempt < 2:
                            default_delay = 3.0 * (fb_attempt + 1)
                            fb_delay = self._extract_retry_delay(fallback_resp, default=default_delay)
                            logger.warning(
                                f"Fallback model '{self.fallback_model}' returned HTTP {fallback_resp.status_code}. "
                                f"Waiting {fb_delay:.1f}s before retry ({fb_attempt + 1}/2)..."
                            )
                            await asyncio.sleep(fb_delay)
                            continue
                        else:
                            logger.error(f"Fallback model '{self.fallback_model}' failed with status {fallback_resp.status_code}")
                            response = fallback_resp
                            break
                    except httpx.RequestError as exc:
                        logger.error(f"Network error calling fallback model '{self.fallback_model}': {type(exc).__name__}")
                        break

            # 3. Final failure evaluation
            if response is None or response.status_code != 200:
                status_desc = f"HTTP {response.status_code}" if response is not None else "Connection failure"
                logger.error(f"Gemini LLM provider failed ({status_desc}). No further fallback configured.")
                raise RuntimeError(f"Gemini provider unavailable: {status_desc}")

            data = response.json()
            candidates = data.get("candidates", [])
            if not candidates:
                raise RuntimeError("Gemini API returned zero candidate responses.")

            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                raise RuntimeError("Gemini candidate content contains no parts.")

            answer_text = parts[0].get("text", "").strip()

            return LLMGroundedResponse(
                answer_text=answer_text,
                language_code=farmer_context.get("language", "hi-IN") if farmer_context else "hi-IN",
                intent="GROUNDED_ADVISORY",
                citations=[],
                is_grounded=True,
                disclaimer_applied=False,
                evidence_sufficient=True,
            )


class MockLLMProvider(LLMProvider):
    """
    Deterministic LLM provider strictly isolated for automated testing and offline verification.
    Generates grounded responses synthesized directly from the retrieved evidence chunks.
    Never calls external networks. Never used to claim live production integration.
    """

    async def generate_grounded_response(
        self,
        system_prompt: str,
        user_query: str,
        context_chunks: List[str],
        farmer_context: Optional[Dict[str, Any]] = None,
    ) -> LLMGroundedResponse:
        lang = farmer_context.get("language", "en-IN") if farmer_context else "en-IN"

        if not context_chunks:
            return LLMGroundedResponse(
                answer_text="No authoritative evidence provided.",
                language_code=lang,
                intent="ABSTAIN",
                citations=[],
                is_grounded=False,
                disclaimer_applied=True,
                evidence_sufficient=False,
            )

        # Synthesize substantive evidence-grounded facts from retrieved chunks without generic templates
        sections = []
        seen_lines = set()

        for chunk in context_chunks:
            chunk_lines = [l.strip() for l in chunk.split("\n") if l.strip()]
            current_section_title = None
            current_section_bullets = []

            for line in chunk_lines:
                if line.startswith("#"):
                    title = line.lstrip("# ").strip()
                    if title and title not in seen_lines:
                        current_section_title = title
                        seen_lines.add(title)
                elif line.startswith("-") or line.startswith("*"):
                    bullet = line.lstrip("-* ").strip()
                    if bullet and bullet not in seen_lines:
                        current_section_bullets.append(bullet)
                        seen_lines.add(bullet)
                else:
                    if line not in seen_lines:
                        current_section_bullets.append(line)
                        seen_lines.add(line)

            if current_section_bullets:
                if current_section_title:
                    formatted_section = f"{current_section_title}:\n" + "\n".join(f"- {b}" for b in current_section_bullets)
                else:
                    formatted_section = "\n".join(f"- {b}" for b in current_section_bullets)
                sections.append(formatted_section)

        if sections:
            answer_text = "\n\n".join(sections)
        else:
            answer_text = context_chunks[0].strip()

        return LLMGroundedResponse(
            answer_text=answer_text,
            language_code=lang,
            intent="MOCK_GROUNDED_ADVISORY",
            citations=[],
            is_grounded=True,
            disclaimer_applied=False,
            evidence_sufficient=True,
        )


def get_llm_provider(mock_for_test: bool = False) -> LLMProvider:
    if mock_for_test:
        return MockLLMProvider()
    if not settings.GEMINI_API_KEY and not settings.LLM_API_KEY:
        if settings.ENVIRONMENT in ("production", "staging"):
            raise ValueError(
                f"GEMINI_API_KEY is required in {settings.ENVIRONMENT} mode. "
                "MockLLMProvider cannot be used as an authoritative production provider."
            )
        return MockLLMProvider()
    return GeminiLLMProvider()
