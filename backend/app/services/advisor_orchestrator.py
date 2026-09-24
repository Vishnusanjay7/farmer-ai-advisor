import uuid
import time
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.core.languages import get_language_config
from backend.app.models.models import FarmerProfile, Conversation, QueryLog, ResponseLog
from backend.app.schemas.advisor import (
    AgriculturalIntent,
    FarmerContextDTO,
    EvidenceItemDTO,
    CitationDTO,
    AdvisorQueryRequest,
    AdvisorQueryResponse,
)
from backend.app.services.query_preprocessor import query_preprocessor
from backend.app.services.intent_classifier import intent_classifier
from backend.app.services.context_extractor import context_extractor
from backend.app.services.retrieval_service import retrieval_service, RetrievalService
from backend.app.services.grounding_validator import grounding_validator, GroundingValidator
from backend.app.providers.llm_provider import LLMProvider, get_llm_provider


class AdvisorOrchestrator:
    """
    Coordinates the 10-layer conversational agricultural RAG pipeline:
    1. Query Preprocessing
    2. Intent Classification
    3. Context Extraction
    4. Specialized Intent-Based Retrieval
    5. Pre-LLM Evidence Validation & Scoring
    6. Grounded Prompt Construction
    7. LLM Provider Execution
    8. Post-LLM Grounding Safety Heuristic
    9. Response & Citation Attribution
    10. Conversation History Persistence
    """

    def __init__(
        self,
        llm_provider: Optional[LLMProvider] = None,
        retrieval: Optional[RetrievalService] = None,
        validator: Optional[GroundingValidator] = None,
    ):
        self.llm_provider = llm_provider or get_llm_provider()
        self.retrieval = retrieval or retrieval_service
        self.validator = validator or grounding_validator

    async def answer_query(
        self,
        db: Session,
        request: AdvisorQueryRequest,
    ) -> AdvisorQueryResponse:
        start_time = time.time()
        query_id = str(uuid.uuid4())
        conv_id = request.conversation_id or str(uuid.uuid4())

        # Check for previous conversation context if conversation_id provided
        inherited_dict = {}
        if request.conversation_id:
            prev_queries = (
                db.query(QueryLog)
                .filter(QueryLog.conversation_id == request.conversation_id)
                .order_by(QueryLog.created_at.desc())
                .all()
            )
            for pq in prev_queries:
                if pq.extracted_entities and isinstance(pq.extracted_entities, dict):
                    for k in ["crop", "variety", "state", "district", "market", "season", "growth_stage", "pest_disease"]:
                        if k in pq.extracted_entities and pq.extracted_entities[k] and k not in inherited_dict:
                            inherited_dict[k] = pq.extracted_entities[k]

        # Layer 1: Query Preprocessing
        preprocessed = query_preprocessor.process(
            query=request.query,
            language=request.language,
            farmer_context=request.farmer_context.model_dump() if request.farmer_context else None,
            request_id=query_id,
        )

        # Layer 2: Intent Classification
        intent, intent_confidence = intent_classifier.classify(preprocessed.normalized_query)

        # Layer 3: Agricultural Context Extraction
        extracted_ctx = context_extractor.extract(
            preprocessed.normalized_query,
            initial_context=request.farmer_context,
        )

        # Multi-turn context inheritance:
        # If the current query omits an entity, inherit it from previous conversation context.
        # If the current query explicitly contains an entity, use the newly extracted entity.
        effective_inherited = {}
        ctx_dict = extracted_ctx.model_dump(exclude_none=True)
        for field, val in inherited_dict.items():
            if field not in ctx_dict or not ctx_dict[field]:
                setattr(extracted_ctx, field, val)
                effective_inherited[field] = val

        # Layer 4: Specialized Intent-Based Retrieval
        evidence = await self.retrieval.retrieve(
            db=db,
            query=preprocessed.normalized_query,
            intent=intent,
            context=extracted_ctx,
            top_k=settings.RAG_TOP_K,
            similarity_threshold=settings.RAG_SIMILARITY_THRESHOLD,
        )

        # Layer 5: Pre-LLM Evidence Validation & Abstention Gate
        is_sufficient, abstention_reason = self.validator.validate_pre_llm(
            intent=intent,
            evidence=evidence,
            similarity_threshold=settings.RAG_SIMILARITY_THRESHOLD,
            language=request.language,
        )

        # Map Citations
        citations = []
        for e in evidence:
            citations.append(
                CitationDTO(
                    title=e.title,
                    issuing_authority=e.issuing_authority,
                    official_url=e.official_url,
                    relevance_score=e.relevance_score,
                    data_origin=e.data_origin,
                    arrival_date=e.metadata.get("arrival_date"),
                )
            )

        # Handle Immediate Abstention (No LLM call)
        if not is_sufficient:
            abstention_msg = self.validator.get_abstention_text(
                language=request.language,
                reason_detail=abstention_reason,
            )
            cat = "UNSUPPORTED" if intent in (AgriculturalIntent.UNSUPPORTED, AgriculturalIntent.UNKNOWN) else "INSUFFICIENT_EVIDENCE"
            response = AdvisorQueryResponse(
                query_id=query_id,
                conversation_id=conv_id,
                original_query=preprocessed.original_query,
                normalized_query=preprocessed.normalized_query,
                language=request.language,
                intent=intent.value,
                input_channel=request.input_channel,
                extracted_context=extracted_ctx.model_dump(exclude_none=True),
                inherited_context=effective_inherited,
                response_text=abstention_msg,
                evidence=evidence,
                citations=citations,
                is_grounded=False,
                abstained=True,
                abstention_reason=abstention_reason,
                data_origin=evidence[0].data_origin if evidence else None,
                llm_called=False,
                response_category=cat,
            )
            self._persist_log(db, response, preprocessed, conv_id, start_time)
            return response

        # Layer 6 & 7: Response Generation (Deterministic for Mandi/Schemes, LLM for Knowledge)
        if intent == AgriculturalIntent.MANDI_PRICE:
            # Deterministic formatting of structured mandi records (QA Requirement 4 & 6)
            top_mandi = evidence[0]
            m = top_mandi.metadata
            origin_badge = "Official source • Live data" if top_mandi.data_origin == "production_live" else "Official source • Cached data"
            variety = m.get("variety")
            grade = m.get("grade")
            vg_str = f"{variety} / {grade}" if variety and grade else (variety or grade or "Standard / FAQ")
            raw_answer = (
                f"Verified Market Price: {m.get('commodity', 'Commodity')} in {m.get('market', 'Market')} Mandi ({m.get('district')}, {m.get('state')}).\n"
                f"- Commodity: {m.get('commodity')}\n"
                f"- Market: {m.get('market')} ({m.get('district')}, {m.get('state')})\n"
                f"- Variety / Grade: {vg_str}\n"
                f"- Minimum Price: ₹{float(m.get('min_price', 0)):.2f}/quintal\n"
                f"- Maximum Price: ₹{float(m.get('max_price', 0)):.2f}/quintal\n"
                f"- Modal Price: ₹{float(m.get('modal_price', 0)):.2f}/quintal\n"
                f"- Arrival Date: {m.get('arrival_date')}\n"
                f"- Source: {m.get('source', top_mandi.issuing_authority)}\n"
                f"- Data Origin: {top_mandi.data_origin} ({origin_badge})"
            )
            llm_called = False
        elif intent == AgriculturalIntent.GOVERNMENT_SCHEME:
            # Deterministic formatting of structured scheme records (QA Requirement 5 & 8)
            top_scheme = evidence[0]
            raw_answer = (
                f"Official Government Scheme: {top_scheme.title}\n"
                f"- Sponsoring Agency: {top_scheme.issuing_authority}\n\n"
                f"{top_scheme.content}\n\n"
                f"Note on Eligibility: Documented eligibility criteria are listed above. Individual farmer eligibility cannot be determined without verifying your specific land records and documentation at the official portal ({top_scheme.official_url})."
            )
            llm_called = False
        else:
            # Grounded Prompt Construction & LLM Provider Execution for Agricultural Knowledge
            lang_cfg = get_language_config(request.language)
            lang_name = lang_cfg.name if lang_cfg else "Indian Regional Language"

            system_prompt = (
                "You are an agricultural advisory assistant for small and marginal Indian farmers.\n"
                "CRITICAL SAFETY RULE: You are NOT the primary source of truth. The official evidence supplied below is.\n"
                "1. Answer ONLY using the facts present in the AUTHORITATIVE EVIDENCE.\n"
                "2. NEVER invent pesticide doses, fertilizer quantities, chemical concentrations, prices, or scheme rules.\n"
                "3. If evidence does not cover a specific detail asked, clearly state that the official documents do not mention it.\n"
                f"4. Respond in {lang_name} ({request.language}).\n"
                "5. Keep the explanation simple, practical, respectful, and accessible to a rural farmer.\n"
                "6. Always mention the issuing authority (e.g., ICAR, Agmarknet, MoA&FW) in the text."
            )

            context_chunks_text = [e.content for e in evidence if e.status == "authoritative"]

            try:
                llm_res = await self.llm_provider.generate_grounded_response(
                    system_prompt=system_prompt,
                    user_query=preprocessed.normalized_query,
                    context_chunks=context_chunks_text,
                    farmer_context=extracted_ctx.model_dump(exclude_none=True),
                )
                raw_answer = llm_res.answer_text
                llm_called = True
            except Exception as e:
                logger.error(f"LLM Provider execution failed: {str(e)}")
                # Fail safely to abstention rather than hallucinating
                abstention_msg = self.validator.get_abstention_text(
                    language=request.language,
                    reason_detail="LLM reasoning service temporarily unavailable",
                )
                response = AdvisorQueryResponse(
                    query_id=query_id,
                    conversation_id=conv_id,
                    original_query=preprocessed.original_query,
                    normalized_query=preprocessed.normalized_query,
                    language=request.language,
                    intent=intent.value,
                    extracted_context=extracted_ctx.model_dump(exclude_none=True),
                    response_text=abstention_msg,
                    evidence=evidence,
                    citations=citations,
                    is_grounded=False,
                    abstained=True,
                    abstention_reason=f"LLM service failure: {str(e)}",
                    data_origin=evidence[0].data_origin if evidence else None,
                    llm_called=False,
                    response_category="INSUFFICIENT_EVIDENCE",
                )
                self._persist_log(db, response, preprocessed, conv_id, start_time)
                return response

        # Layer 8: Post-LLM Grounding Safety Heuristic
        is_post_valid, post_reason = self.validator.validate_post_llm(
            generated_text=raw_answer,
            evidence=evidence,
            intent=intent,
        )

        if not is_post_valid:
            logger.warning(f"Post-LLM Grounding Check Failed: {post_reason}")
            safe_text = self.validator.get_abstention_text(
                language=request.language,
                reason_detail=post_reason,
            )
            response = AdvisorQueryResponse(
                query_id=query_id,
                conversation_id=conv_id,
                original_query=preprocessed.original_query,
                normalized_query=preprocessed.normalized_query,
                language=request.language,
                intent=intent.value,
                input_channel=request.input_channel,
                extracted_context=extracted_ctx.model_dump(exclude_none=True),
                inherited_context=effective_inherited,
                response_text=safe_text,
                evidence=evidence,
                citations=citations,
                is_grounded=False,
                abstained=True,
                abstention_reason=post_reason,
                data_origin=evidence[0].data_origin if evidence else None,
                llm_called=True,
                response_category="INSUFFICIENT_EVIDENCE",
            )
            self._persist_log(db, response, preprocessed, conv_id, start_time)
            return response

        # Layer 9: Response Formatter & Attribution
        primary_origin = evidence[0].data_origin if evidence else "production_cached"

        response = AdvisorQueryResponse(
            query_id=query_id,
            conversation_id=conv_id,
            original_query=preprocessed.original_query,
            normalized_query=preprocessed.normalized_query,
            language=request.language,
            intent=intent.value,
            input_channel=request.input_channel,
            extracted_context=extracted_ctx.model_dump(exclude_none=True),
            inherited_context=effective_inherited,
            response_text=raw_answer,
            evidence=evidence,
            citations=citations,
            is_grounded=True,
            abstained=False,
            abstention_reason=None,
            data_origin=primary_origin,
            llm_called=llm_called,
            response_category="GROUNDED_ADVISORY",
        )

        # Layer 10: Conversation Persistence
        self._persist_log(db, response, preprocessed, conv_id, start_time)

        return response

    def _persist_log(
        self,
        db: Session,
        response: AdvisorQueryResponse,
        preprocessed,
        conv_id: str,
        start_time: float,
    ):
        """Safely logs query and response to database without breaking on DB lock/absence."""
        try:
            latency_ms = int((time.time() - start_time) * 1000)

            # Ensure default guest farmer exists
            farmer = db.query(FarmerProfile).filter(FarmerProfile.session_id == "guest-farmer-profile").first()
            if not farmer:
                farmer = FarmerProfile(
                    id=str(uuid.uuid4()),
                    session_id="guest-farmer-profile",
                    preferred_language=response.language,
                    state="All-India",
                    district="General",
                )
                db.add(farmer)
                db.flush()

            # Ensure conversation exists
            conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
            if not conv:
                conv = Conversation(
                    id=conv_id,
                    farmer_id=farmer.id,
                    title=f"Advisory Query: {response.original_query[:40]}",
                )
                db.add(conv)
                db.flush()

            # Log Query
            q_log = QueryLog(
                id=response.query_id,
                conversation_id=conv.id,
                farmer_id=farmer.id,
                input_channel=response.input_channel,
                detected_language=response.language,
                raw_transcript=response.original_query,
                classified_intent=response.intent,
                extracted_entities=response.extracted_context,
            )
            db.add(q_log)
            db.flush()

            # Log Response
            r_log = ResponseLog(
                id=str(uuid.uuid4()),
                query_id=q_log.id,
                response_text=response.response_text,
                is_grounded=response.is_grounded,
                confidence_score=0.95 if response.is_grounded else 0.0,
                disclaimer_applied=response.abstained,
                retrieved_sources=[c.model_dump() for c in response.citations],
                latency_breakdown_ms={"total_ms": latency_ms, "llm_called": response.llm_called},
            )
            db.add(r_log)
            db.commit()
        except Exception as e:
            logger.warning(f"Failed to persist query/response log to database: {str(e)}")
            db.rollback()


advisor_orchestrator = AdvisorOrchestrator()
