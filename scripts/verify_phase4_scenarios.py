import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncio
import json
from datetime import date
from sqlalchemy.orm import Session

from backend.app.db.session import SessionLocal, engine, Base
from backend.app.schemas.advisor import AdvisorQueryRequest, FarmerContextDTO
from backend.app.services.advisor_orchestrator import advisor_orchestrator
from backend.app.providers.llm_provider import MockLLMProvider
from backend.app.models.models import MandiPrice, GovernmentScheme, SourceDocument, KnowledgeChunk


SCENARIOS = [
    {
        "id": "A",
        "name": "Scenario A",
        "query": "What fertilizer schedule should be followed for Wheat in Punjab?",
        "language": "en-IN",
        "context": None,
    },
    {
        "id": "B",
        "name": "Scenario B",
        "query": "How to control yellow stem borer in paddy?",
        "language": "en-IN",
        "context": None,
    },
    {
        "id": "C",
        "name": "Scenario C",
        "query": "Who is eligible for PM-KISAN scheme and what documents are required?",
        "language": "en-IN",
        "context": None,
    },
    {
        "id": "D",
        "name": "Scenario D",
        "query": "What is the wheat price in Indore mandi?",
        "language": "en-IN",
        "context": FarmerContextDTO(crop="Wheat", state="Madhya Pradesh", district="Indore", market="Indore"),
    },
    {
        "id": "E",
        "name": "Scenario E",
        "query": "What is the drone spraying schedule for dragon fruit in Ladakh?",
        "language": "en-IN",
        "context": None,
    },
    {
        "id": "F",
        "name": "Scenario F",
        "query": "Who won the cricket match yesterday?",
        "language": "en-IN",
        "context": None,
    },
]


async def run_scenario_verification():
    db: Session = SessionLocal()
    orchestrator = advisor_orchestrator
    orchestrator.llm_provider = MockLLMProvider()

    # Ensure a valid mandi record exists in Indore for scenario D
    existing_mandi = db.query(MandiPrice).filter(
        MandiPrice.commodity == "Wheat",
        MandiPrice.market == "Indore",
        MandiPrice.data_origin == "production_live",
    ).first()
    if not existing_mandi:
        db.add(
            MandiPrice(
                state="Madhya Pradesh",
                district="Indore",
                market="Indore",
                commodity="Wheat",
                variety="Lokwan",
                grade="FAQ",
                arrival_date=date(2026, 9, 22),
                min_price=2450.0,
                max_price=2850.0,
                modal_price=2650.0,
                source="Agmarknet",
                data_origin="production_live",
            )
        )
        db.commit()

    results = []

    for sc in SCENARIOS:
        req = AdvisorQueryRequest(
            query=sc["query"],
            language=sc["language"],
            farmer_context=sc["context"],
        )
        res = await orchestrator.answer_query(db, req)

        record = {
            "scenario": sc["id"],
            "original_question": res.original_query,
            "normalized_question": res.normalized_query,
            "language": res.language,
            "detected_intent": res.intent,
            "extracted_context": res.extracted_context,
            "retrieval_source": res.evidence[0].issuing_authority if res.evidence else "None",
            "retrieved_evidence": (res.evidence[0].content[:200] + "...") if res.evidence else "None",
            "relevance_score": res.evidence[0].relevance_score if res.evidence else 0.0,
            "llm_called": "YES" if res.llm_called else "NO",
            "exact_final_response_text": res.response_text,
            "citations": [
                {
                    "title": c.title,
                    "issuing_authority": c.issuing_authority,
                    "official_url": c.official_url,
                    "relevance_score": c.relevance_score,
                    "data_origin": c.data_origin,
                }
                for c in res.citations
            ],
            "data_origin": res.data_origin or "None",
            "abstained": "YES" if res.abstained else "NO",
            "abstention_reason": res.abstention_reason or "N/A",
        }
        results.append(record)

    db.close()
    out_path = os.path.join(os.path.dirname(__file__), "qa_scenario_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Results written successfully to {out_path}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(run_scenario_verification())
