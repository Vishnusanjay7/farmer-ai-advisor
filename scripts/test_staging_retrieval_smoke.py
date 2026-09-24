import os
import sys
import asyncio
import json

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Load .env.staging
staging_env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env.staging"))
if os.path.exists(staging_env_path):
    from dotenv import load_dotenv
    load_dotenv(staging_env_path)

from backend.app.core.config import settings

if settings.ENVIRONMENT != "staging":
    print(f"FATAL: Staging retrieval smoke tests require explicit ENVIRONMENT=staging. Current: '{settings.ENVIRONMENT}'. Aborting.")
    sys.exit(1)

if not settings.DATABASE_URL or "sqlite" in settings.DATABASE_URL.lower():
    print("FATAL: Staging smoke tests require a valid PostgreSQL DATABASE_URL. SQLite is strictly rejected.")
    sys.exit(1)

if not settings.GEMINI_API_KEY:
    print("FATAL: GEMINI_API_KEY is required for staging smoke tests.")
    sys.exit(1)

from backend.app.db.session import SessionLocal
from backend.app.schemas.advisor import AdvisorQueryRequest
from backend.app.services.advisor_orchestrator import advisor_orchestrator
from backend.app.providers.embedding_provider import GeminiEmbeddingProvider
from backend.app.providers.llm_provider import GeminiLLMProvider

SMOKE_TESTS = [
    {
        "id": "A",
        "category": "Wheat irrigation / crop advisory",
        "query": "What irrigation schedule should be followed for Wheat in Punjab?",
    },
    {
        "id": "B",
        "category": "Wheat yellow rust / pest-disease",
        "query": "What should I do if Wheat has yellow rust?",
    },
    {
        "id": "C",
        "category": "PM-KISAN",
        "query": "What is PM-KISAN and who can benefit from it?",
    },
    {
        "id": "D",
        "category": "Unsupported agricultural topic",
        "query": "What is the recommended treatment for dragon fruit disease in Ladakh?",
    },
    {
        "id": "E",
        "category": "Non-agricultural question",
        "query": "What is the score of today's cricket match?",
    },
]


async def run_staging_smoke_tests():
    print("=" * 70)
    print("PHASE 7 TASK 2C: REAL STAGING RETRIEVAL SMOKE TESTS")
    print("Target: Supabase PostgreSQL Staging + Gemini Embedding / LLM")
    print("=" * 70)

    db = SessionLocal()
    orchestrator = advisor_orchestrator

    # Verify live providers are active
    print(f"\n[Provider Verification]")
    print(f"  - ENVIRONMENT: {settings.ENVIRONMENT}")
    print(f"  - LLM Provider: {type(orchestrator.llm_provider).__name__}")
    print(f"  - Embedding Provider: {type(orchestrator.retrieval.embedding_provider).__name__}")
    print(f"  - Embedding Model: {getattr(orchestrator.retrieval.embedding_provider, 'model', 'N/A')}")
    print(f"  - Database Host: {settings.DATABASE_URL.split('@')[-1] if settings.DATABASE_URL else 'None'}\n")

    results = []

    for test in SMOKE_TESTS:
        print("-" * 70)
        print(f"TEST {test['id']}: {test['category']}")
        print(f"Query: \"{test['query']}\"")
        print("-" * 70)

        req = AdvisorQueryRequest(
            query=test["query"],
            language="en-IN",
        )

        res = await orchestrator.answer_query(db, req)

        # Extract source names and details
        source_names = [e.issuing_authority for e in res.evidence] if res.evidence else []
        top_score = res.evidence[0].relevance_score if res.evidence else 0.0

        record = {
            "id": test["id"],
            "category": test["category"],
            "query": test["query"],
            "intent": res.intent,
            "extracted_context": res.extracted_context,
            "retrieved_source_count": len(res.evidence),
            "top_relevance_score": top_score,
            "source_names": source_names,
            "data_origin": res.data_origin,
            "llm_called": res.llm_called,
            "is_grounded": res.is_grounded,
            "abstained": res.abstained,
            "abstention_reason": res.abstention_reason,
            "response_category": res.response_category,
            "response_text_snippet": res.response_text[:250] + ("..." if len(res.response_text) > 250 else ""),
        }
        results.append(record)

        print(f"  - Intent:                 {record['intent']}")
        print(f"  - Extracted Context:       {record['extracted_context']}")
        print(f"  - Retrieved Source Count:  {record['retrieved_source_count']}")
        print(f"  - Top Relevance Score:     {record['top_relevance_score']:.4f}")
        print(f"  - Source Names:            {record['source_names'][:3]}")
        print(f"  - Data Origin:             {record['data_origin']}")
        print(f"  - LLM Called:              {record['llm_called']}")
        print(f"  - Grounded:                {record['is_grounded']}")
        print(f"  - Abstained:               {record['abstained']}")
        if record['abstained']:
            print(f"  - Abstention Reason:       {record['abstention_reason']}")
        print(f"  - Response Category:       {record['response_category']}")
        print(f"  - Response Text Snippet:\n    \"{record['response_text_snippet']}\"\n")

    db.close()
    return results


if __name__ == "__main__":
    asyncio.run(run_staging_smoke_tests())
