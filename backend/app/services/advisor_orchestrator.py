import re
import uuid
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from fastapi import HTTPException, status
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
        current_user: Optional[Any] = None,
    ) -> AdvisorQueryResponse:
        start_time = time.time()
        query_id = str(uuid.uuid4())
        conv_id = request.conversation_id or str(uuid.uuid4())

        # Check conversation ownership if conversation_id was provided
        if request.conversation_id:
            existing_conv = db.query(Conversation).filter(Conversation.id == request.conversation_id).first()
            if existing_conv and existing_conv.farmer and existing_conv.farmer.session_id.startswith("user-"):
                owner_user_id = existing_conv.farmer.session_id.removeprefix("user-")
                if not current_user or str(current_user.id) != owner_user_id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail={
                            "error_code": "FORBIDDEN",
                            "message": "You do not have access to this conversation.",
                        },
                    )

        # Check for previous conversation context if conversation_id provided
        inherited_dict = {}
        prev_intent = None
        if request.conversation_id:
            prev_queries = (
                db.query(QueryLog)
                .filter(QueryLog.conversation_id == request.conversation_id)
                .order_by(QueryLog.created_at.desc())
                .all()
            )
            if prev_queries:
                prev_intent = prev_queries[0].classified_intent
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
        raw_intent, intent_confidence = intent_classifier.classify(preprocessed.normalized_query)

        # Contextual intent resolution:
        # If current query was classified as UNSUPPORTED (e.g. follow-up phrase "What about tomorrow?"),
        # check if it is an explicit out-of-scope query (e.g. cricket, politics).
        # If NOT explicitly out-of-scope, and a valid agricultural intent was established in previous turns,
        # inherit the prior conversation intent.
        intent = raw_intent
        is_explicit_out_of_scope = any(
            re.search(p, preprocessed.normalized_query.lower())
            for p in intent_classifier.OUT_OF_SCOPE_KEYWORDS
        )
        if intent == AgriculturalIntent.UNSUPPORTED and not is_explicit_out_of_scope:
            if prev_intent and prev_intent not in (AgriculturalIntent.UNSUPPORTED.value, AgriculturalIntent.UNKNOWN.value):
                try:
                    intent = AgriculturalIntent(prev_intent)
                except ValueError:
                    pass

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
                # Location conflict guard: do not inherit a state that contradicts the query's district
                if field == "state" and extracted_ctx.district:
                    canonical_state = context_extractor.DISTRICT_TO_STATE.get(extracted_ctx.district)
                    if canonical_state and canonical_state != val:
                        continue
                # Do not inherit a district that contradicts the query's state
                if field == "district" and extracted_ctx.state:
                    canonical_state = context_extractor.DISTRICT_TO_STATE.get(val)
                    if canonical_state and canonical_state != extracted_ctx.state:
                        continue
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
            self._persist_log(db, response, preprocessed, conv_id, start_time, current_user=current_user)
            return response

        # Layer 6 & 7: Response Generation (Deterministic for Mandi/Schemes, LLM for Knowledge)
        has_tomorrow = bool(re.search(r"\b(tomorrow|future|next day|kal|நாளை|రేపు|उद्या|നാളെ|ਕੱਲ੍ਹ|ଆସନ୍ତାକାଲି)\b", preprocessed.normalized_query.lower()))

        if intent == AgriculturalIntent.MANDI_PRICE:
            # Deterministic formatting of structured mandi records in regional language
            top_mandi = evidence[0]
            raw_answer = self._format_mandi_response(top_mandi.metadata, top_mandi, request.language, has_tomorrow)
            llm_called = False
        elif intent in (AgriculturalIntent.GOVERNMENT_SCHEME, AgriculturalIntent.CROP_INSURANCE, AgriculturalIntent.AGRICULTURAL_CREDIT):
            # Deterministic formatting of structured scheme records in regional language
            top_scheme = evidence[0]
            raw_answer = self._format_scheme_response(top_scheme, request.language)
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
                farmer_ctx_dict = extracted_ctx.model_dump()
                farmer_ctx_dict["language"] = request.language
                llm_res = await self.llm_provider.generate_grounded_response(
                    system_prompt=system_prompt,
                    user_query=preprocessed.normalized_query,
                    context_chunks=context_chunks_text,
                    farmer_context=farmer_ctx_dict,
                )
                raw_answer = llm_res.answer_text
                llm_called = True
            except Exception as e:
                logger.error(f"LLM Provider invocation failed: {e}", exc_info=True)
                raw_answer = self.validator.get_abstention_text(
                    language=request.language,
                    reason_detail="Upstream model error occurred while generating grounded answer.",
                )
                llm_called = False

        # Layer 8: Post-LLM Grounding Safety Heuristic
        is_safe, failure_reason = self.validator.validate_post_llm(
            generated_text=raw_answer,
            evidence=evidence,
            intent=intent,
        )

        final_response_text = raw_answer
        is_grounded = True
        abstained = False

        if not is_safe:
            logger.warning(f"Post-LLM safety check failed: {failure_reason}. Falling back to safe abstention.")
            final_response_text = self.validator.get_abstention_text(
                language=request.language,
                reason_detail=failure_reason,
            )
            is_grounded = False
            abstained = True

        # Layer 9: Safety Disclaimer Application (QA Requirement 8)
        # Apply standard disclaimer only if answer is informational and not already abstained
        if not abstained and intent not in (AgriculturalIntent.MANDI_PRICE, AgriculturalIntent.GOVERNMENT_SCHEME, AgriculturalIntent.CROP_INSURANCE, AgriculturalIntent.AGRICULTURAL_CREDIT):
            disclaimer = {
                "hi-IN": "\n\n(सलाह: किसी भी रासायनिक छिड़काव से पहले स्थानीय कृषि विज्ञान केंद्र (KVK) या कृषि अधिकारी से पुष्टि अवश्य करें।)",
                "te-IN": "\n\n(సలహా: ఏదైనా రసాయన పిచికారీ చేయడానికి ముందు స్థానిక కృషి విజ్ఞాన కేంద్రం (KVK) లేదా వ్యవసాయ అధికారిని సంప్రదించండి.)",
                "ta-IN": "\n\n(குறிப்பு: ரசாயன தெளிப்புக்கு முன் உள்ளூர் கேவிகே (KVK) அல்லது வேளாண்மை அலுவலரை கலந்தாலோசிக்கவும்.)",
                "mr-IN": "\n\n(सल्ला: फवारणीपूर्वी स्थानिक कृषी विज्ञान केंद्र (KVK) किंवा कृषी अधिकाऱ्यांचा सल्ला घ्यावा.)",
                "kn-IN": "\n\n(ಸಲಹೆ: ಯಾವುದೇ ಸಿಂಪಡಣೆಗೆ ಮುನ್ನ ಸ್ಥಳೀಯ ಕೃಷಿ ವಿಜ್ಞಾನ ಕೇಂದ್ರ (KVK) ಅಥವಾ ಕೃಷಿ ಅಧಿಕಾರಿಯನ್ನು ಸಂಪರ್ಕಿಸಿ.)",
                "bn-IN": "\n\n(পরামর্শ: কোনো রাসায়নিক স্প্রে করার আগে স্থানীয় কৃষি বিজ্ঞান কেন্দ্র (KVK) বা কৃষি কর্মকর্তার সাথে পরামর্শ করুন।)",
                "gu-IN": "\n\n(સલાહ: કોઈપણ છંટકાવ કરતા પહેલા સ્થાનિક કૃષિ વિજ્ઞાન કેન્દ્ર (KVK) અથવા કૃષિ અધિકારીનો સંપર્ક કરો.)",
                "ml-IN": "\n\n(നിർദ്ദേശം: രാസവസ്തുക്കൾ പ്രയോഗിക്കുന്നതിന് മുൻപ് പ്രാദേശിക കൃഷി വിജ്ഞാന കേന്ദ്രവുമായോ (KVK) കൃഷി ഓഫീസറുമായോ ബന്ധപ്പെടുക.)",
                "pa-IN": "\n\n(ਸਲਾਹ: ਕਿਸੇ ਵੀ ਰਸਾਇਣਕ ਸਪਰੇਅ ਤੋਂ ਪਹਿਲਾਂ ਸਥਾਨਕ ਕ੍ਰਿਸ਼ੀ ਵਿਗਿਆਨ ਕੇਂਦਰ (KVK) ਜਾਂ ਖੇਤੀਬਾੜੀ ਅਧਿਕਾਰੀ ਨਾਲ ਸਲਾਹ ਕਰੋ।)",
                "od-IN": "\n\n(ପରାମର୍ଶ: କୌଣସି ରାସାୟନିକ ସିଞ୍ଚନ ପୂର୍ବରୁ ସ୍ଥାନୀୟ କୃଷି ବିଜ୍ଞାନ କେନ୍ଦ୍ର (KVK) ବା କୃଷି ଅଧିକାରୀଙ୍କ ପରାମର୍ଶ ନିଅନ୍ତୁ।)",
                "en-IN": "\n\n(Advisory Note: Always confirm with your local Krishi Vigyan Kendra (KVK) or agriculture extension officer before applying chemical treatments.)",
            }
            lang_code = request.language if request.language != "or-IN" else "od-IN"
            final_response_text += disclaimer.get(lang_code, disclaimer["en-IN"])

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
            response_text=final_response_text,
            evidence=evidence,
            citations=citations,
            is_grounded=is_grounded,
            abstained=abstained,
            abstention_reason=failure_reason if abstained else None,
            data_origin=evidence[0].data_origin if evidence else None,
            llm_called=llm_called,
            response_category="GROUNDED_ADVISORY",
        )

        # Layer 10: Conversation Persistence
        self._persist_log(db, response, preprocessed, conv_id, start_time, current_user=current_user)

        return response

    def _format_mandi_response(
        self,
        m: Dict[str, Any],
        top_mandi: EvidenceItemDTO,
        language: str,
        has_tomorrow: bool,
    ) -> str:
        """Formats structured mandi evidence into natural grounded regional language text."""
        lang_key = language if language != "or-IN" else "od-IN"
        commodity = m.get("commodity", "Commodity")
        market = m.get("market", "Market")
        district = m.get("district", "")
        state = m.get("state", "")
        variety = m.get("variety")
        grade = m.get("grade")
        vg_str = f"{variety} / {grade}" if variety and grade else (variety or grade or "Standard / FAQ")
        min_p = float(m.get("min_price", 0))
        max_p = float(m.get("max_price", 0))
        modal_p = float(m.get("modal_price", 0))
        arrival_date = m.get("arrival_date", "")
        source = m.get("source", top_mandi.issuing_authority)
        origin = top_mandi.data_origin

        if lang_key == "ta-IN":
            origin_badge = "அதிகாரப்பூர்வ ஆதாரம் • சமீபத்திய தினசரி தரவு" if origin == "production_live" else "அதிகாரப்பூர்வ ஆதாரம் • சேமிக்கப்பட்ட தரவு"
            text = (
                f"சரிபார்க்கப்பட்ட சந்தை விலை: {market} சந்தையில் {commodity} ({district}, {state}).\n"
                f"- பயிர்/பொருள்: {commodity}\n"
                f"- சந்தை: {market} ({district}, {state})\n"
                f"- வகை / தரம்: {vg_str}\n"
                f"- குறைந்தபட்ச விலை: ₹{min_p:.2f}/குவிண்டால்\n"
                f"- அதிகபட்ச விலை: ₹{max_p:.2f}/குவிண்டால்\n"
                f"- மாதிரி விலை: ₹{modal_p:.2f}/குவிண்டால்\n"
                f"- வரத்து தேதி: {arrival_date}\n"
                f"- ஆதாரம்: {source}\n"
                f"- தரவு நிலை: {origin} ({origin_badge})"
            )
            if has_tomorrow:
                text += "\n- குறிப்பு: நாளைய அதிகாரப்பூர்வ சந்தை விலைகள் முன்கூட்டியே வெளியிடப்படுவதில்லை. சமீபத்திய சரிபார்க்கப்பட்ட தினசரி வரத்து தரவு காட்டப்படுகிறது."
            return text

        elif lang_key == "hi-IN":
            origin_badge = "आधिकारिक स्रोत • नवीनतम उपलब्ध दैनिक डेटा" if origin == "production_live" else "आधिकारिक स्रोत • संचित डेटा"
            text = (
                f"सत्यापित मंडी भाव: {market} मंडी में {commodity} ({district}, {state})।\n"
                f"- फसल/जिंस: {commodity}\n"
                f"- मंडी: {market} ({district}, {state})\n"
                f"- किस्म / श्रेणी: {vg_str}\n"
                f"- न्यूनतम भाव: ₹{min_p:.2f}/क्विंटल\n"
                f"- अधिकतम भाव: ₹{max_p:.2f}/क्विंटल\n"
                f"- मॉडल (औसत) भाव: ₹{modal_p:.2f}/क्विंटल\n"
                f"- आवक दिनांक: {arrival_date}\n"
                f"- स्रोत: {source}\n"
                f"- डेटा स्थिति: {origin} ({origin_badge})"
            )
            if has_tomorrow:
                text += "\n- नोट: कल के आधिकारिक भाव पहले से प्रकाशित नहीं होते हैं। नवीनतम सत्यापित दैनिक आवक डेटा प्रदर्शित किया जा रहा है।"
            return text

        elif lang_key == "te-IN":
            origin_badge = "అధికారిక మూలం • తాజా రోజువారీ డేటా" if origin == "production_live" else "అధికారిక మూలం • కాష్ చేసిన డేటా"
            text = (
                f"ధృవీకరించబడిన మార్కెట్ ధర: {market} మార్కెట్‌లో {commodity} ({district}, {state}).\n"
                f"- పంట/వస్తువు: {commodity}\n"
                f"- మార్కెట్: {market} ({district}, {state})\n"
                f"- రకం / గ్రేడ్: {vg_str}\n"
                f"- కనిష్ట ధర: ₹{min_p:.2f}/క్వింటాల్\n"
                f"- గరిష్ట ధర: ₹{max_p:.2f}/క్వింటాల్\n"
                f"- మోడల్ (సగటు) ధర: ₹{modal_p:.2f}/క్వింటాల్\n"
                f"- వచ్చిన తేదీ: {arrival_date}\n"
                f"- మూలం: {source}\n"
                f"- డేటా స్థితి: {origin} ({origin_badge})"
            )
            if has_tomorrow:
                text += "\n- గమనిక: రేపటి అధికారిక మార్కెట్ ధరలు ముందుగా ప్రచురించబడవు. తాజా ధృవీకరించబడిన రోజువారీ రాక డేటా చూపబడుతోంది."
            return text

        elif lang_key == "mr-IN":
            origin_badge = "अधिकृत स्त्रोत • नवीनतम दैनिक माहिती" if origin == "production_live" else "अधिकृत स्त्रोत • कॅश केलेली माहिती"
            text = (
                f"पडताळणी केलेले बाजारभाव: {market} बाजारामध्ये {commodity} ({district}, {state}).\n"
                f"- शेतमाल: {commodity}\n"
                f"- बाजार समिती: {market} ({district}, {state})\n"
                f"- वाण / प्रत: {vg_str}\n"
                f"- किमान भाव: ₹{min_p:.2f}/क्विंटल\n"
                f"- कमाल भाव: ₹{max_p:.2f}/क्विंटल\n"
                f"- सर्वसाधारण भाव: ₹{modal_p:.2f}/क्विंटल\n"
                f"- आवक दिनांक: {arrival_date}\n"
                f"- स्त्रोत: {source}\n"
                f"- डेटा स्थिती: {origin} ({origin_badge})"
            )
            if has_tomorrow:
                text += "\n- टीप: उद्याचे अधिकृत बाजारभाव आगाऊ जाहीर केले जात नाहीत. नवीनतम पडताळणी केलेली दैनिक आवक माहिती दर्शविली जात आहे."
            return text

        elif lang_key == "kn-IN":
            origin_badge = "ಅಧಿಕೃತ ಮೂಲ • ಇತ್ತೀಚಿನ ದೈನಂದಿನ ಮಾಹಿತಿ" if origin == "production_live" else "ಅಧಿಕೃತ ಮೂಲ • ಸಂಗ್ರಹಿಸಿದ ಮಾಹಿತಿ"
            text = (
                f"ಪರಿಶೀಲಿಸಿದ ಮಾರುಕಟ್ಟೆ ದರ: {market} ಮಾರುಕಟ್ಟೆಯಲ್ಲಿ {commodity} ({district}, {state}).\n"
                f"- ಬೆಳೆ/ವಸ್ತು: {commodity}\n"
                f"- ಮಾರುಕಟ್ಟೆ: {market} ({district}, {state})\n"
                f"- ತಳಿ / ದರ್ಜೆ: {vg_str}\n"
                f"- ಕನಿಷ್ಠ ದರ: ₹{min_p:.2f}/ಕ್ವಿಂಟಾಲ್\n"
                f"- ಗರಿಷ್ಠ ದರ: ₹{max_p:.2f}/ಕ್ವಿಂಟಾಲ್\n"
                f"- ಮಾದರಿ ದರ: ₹{modal_p:.2f}/ಕ್ವಿಂಟಾಲ್\n"
                f"- ಆವಕ ದಿನಾಂಕ: {arrival_date}\n"
                f"- ಮೂಲ: {source}\n"
                f"- ಮಾಹಿತಿ ಮೂಲ: {origin} ({origin_badge})"
            )
            if has_tomorrow:
                text += "\n- ಟಿಪ್ಪಣಿ: ನಾಳೆಯ ಅಧಿಕೃತ ಮಾರುಕಟ್ಟೆ ದರಗಳು ಮುಂಚಿತವಾಗಿ ಪ್ರಕಟವಾಗುವುದಿಲ್ಲ. ಇತ್ತೀಚಿನ ಪರಿಶೀಲಿಸಿದ ದೈನಂದಿನ ಆವಕ ಮಾಹಿತಿಯನ್ನು ಪ್ರದರ್ಶಿಸಲಾಗುತ್ತಿದೆ."
            return text

        elif lang_key == "bn-IN":
            origin_badge = "অফিসিয়াল উৎস • সর্বশেষ দৈনিক তথ্য" if origin == "production_live" else "অফিসিয়াল উৎস • ক্যাশ করা তথ্য"
            text = (
                f"যাচাইকৃত বাজার দর: {market} মান্ডিতে {commodity} ({district}, {state})।\n"
                f"- ফসল/পণ্য: {commodity}\n"
                f"- মান্ডি: {market} ({district}, {state})\n"
                f"- জাত / গ্রেড: {vg_str}\n"
                f"- সর্বনিম্ন দর: ₹{min_p:.2f}/কুইন্টাল\n"
                f"- সর্বোচ্চ দর: ₹{max_p:.2f}/কুইন্টাল\n"
                f"- গড় (মডেল) দর: ₹{modal_p:.2f}/কুইন্টাল\n"
                f"- আমদানি তারিখ: {arrival_date}\n"
                f"- উৎস: {source}\n"
                f"- উপাত্তের অবস্থা: {origin} ({origin_badge})"
            )
            if has_tomorrow:
                text += "\n- নোট: আগামীকালের অফিসিয়াল বাজার দর আগে থেকে প্রকাশিত হয় না। সর্বশেষ যাচাইকৃত দৈনিক আগমনের তথ্য দেখানো হচ্ছে।"
            return text

        elif lang_key == "gu-IN":
            origin_badge = "સત્તાવાર સ્ત્રોત • તાજેતરનો દૈનિક ડેટા" if origin == "production_live" else "સત્તાવાર સ્ત્રોત • કેશ્ડ ડેટા"
            text = (
                f"ચકાસાયેલ માર્કેટ ભાવ: {market} માર્કેટમાં {commodity} ({district}, {state}).\n"
                f"- પાક: {commodity}\n"
                f"- માર્કેટ: {market} ({district}, {state})\n"
                f"- જાત / ગ્રેડ: {vg_str}\n"
                f"- ન્યૂનતમ ભાવ: ₹{min_p:.2f}/ક્વિન્ટલ\n"
                f"- મહત્તમ ભાવ: ₹{max_p:.2f}/ક્વિન્ટલ\n"
                f"- મોડલ ભાવ: ₹{modal_p:.2f}/ક્વિન્ટલ\n"
                f"- આવક તારીખ: {arrival_date}\n"
                f"- સ્ત્રોત: {source}\n"
                f"- ડેટા સ્થિતિ: {origin} ({origin_badge})"
            )
            if has_tomorrow:
                text += "\n- નોંધ: આવતીકાલના સત્તાવાર બજાર ભાવો અગાઉથી પ્રકાશિત થતા નથી. નવીનતમ ચકાસાયેલ દૈનિક આવક ડેટા દર્શાવવામાં આવી રહ્યો છે."
            return text

        elif lang_key == "ml-IN":
            origin_badge = "ഔദ്യോഗിക ഉറവിടം • ഏറ്റവും പുതിയ പ്രതിദിന ഡാറ്റ" if origin == "production_live" else "ഔദ്യോഗിക ഉറവിടം • കാഷെ ചെയ്ത ഡാറ്റ"
            text = (
                f"സ്ഥിരീകരിച്ച മാർക്കറ്റ് നിരക്ക്: {market} വിപണിയിൽ {commodity} ({district}, {state}).\n"
                f"- വിള: {commodity}\n"
                f"- മാർക്കറ്റ്: {market} ({district}, {state})\n"
                f"- ഇനം / ഗ്രേഡ്: {vg_str}\n"
                f"- കുറഞ്ഞ നിരക്ക്: ₹{min_p:.2f}/ക്വിന്റൽ\n"
                f"- കൂടിയ നിരക്ക്: ₹{max_p:.2f}/ക്വിന്റൽ\n"
                f"- ശരാശരി നിരക്ക്: ₹{modal_p:.2f}/ക്വിന്റൽ\n"
                f"- എത്തിയ തീയതി: {arrival_date}\n"
                f"- ഉറവിടം: {source}\n"
                f"- ഡാറ്റ നില: {origin} ({origin_badge})"
            )
            if has_tomorrow:
                text += "\n- കുറിപ്പ്: നാളത്തെ ഔദ്യോഗിക മാർക്കറ്റ് നിരക്കുകൾ മുൻകൂട്ടി പ്രസിദ്ധീകരിക്കാറില്ല. ഏറ്റവും പുതിയ പരിശോധിച്ച പ്രതിദിന വരവ് ഡാറ്റയാണ് പ്രദർശിപ്പിക്കുന്നത്."
            return text

        elif lang_key == "pa-IN":
            origin_badge = "ਸਰਕਾਰੀ ਸਰੋਤ • ਤਾਜ਼ਾ ਰੋਜ਼ਾਨਾ ਡੇਟਾ" if origin == "production_live" else "ਸਰਕਾਰੀ ਸਰੋਤ • ਕੈਸ਼ ਡੇਟਾ"
            text = (
                f"ਪ੍ਰਮਾਣਿਤ ਮੰਡੀ ਭਾਅ: {market} ਮੰਡੀ ਵਿੱਚ {commodity} ({district}, {state})।\n"
                f"- ਫ਼ਸਲ: {commodity}\n"
                f"- ਮੰਡੀ: {market} ({district}, {state})\n"
                f"- ਕਿਸਮ / ਗ੍ਰੇਡ: {vg_str}\n"
                f"- ਘੱਟੋ-ਘੱਟ ਭਾਅ: ₹{min_p:.2f}/ਕੁਇੰਟਲ\n"
                f"- ਵੱਧ ਤੋਂ ਵੱਧ ਭਾਅ: ₹{max_p:.2f}/ਕੁਇੰਟਲ\n"
                f"- ਮਾਡਲ ਭਾਅ: ₹{modal_p:.2f}/ਕੁਇੰਟਲ\n"
                f"- ਆਮਦ ਮਿਤੀ: {arrival_date}\n"
                f"- ਸਰੋਤ: {source}\n"
                f"- ਡੇਟਾ ਸਥਿਤੀ: {origin} ({origin_badge})"
            )
            if has_tomorrow:
                text += "\n- ਨੋਟ: ਕੱਲ੍ਹ ਦੇ ਅਧਿਕਾਰਤ ਭਾਅ ਪਹਿਲਾਂ ਤੋਂ ਪ੍ਰਕਾਸ਼ਿਤ ਨਹੀਂ ਹੁੰਦੇ। ਤਾਜ਼ਾ ਤਸਦੀਕਸ਼ੁਦਾ ਰੋਜ਼ਾਨਾ ਆਮਦ ਡੇਟਾ ਦਿਖਾਇਆ ਜਾ ਰਿਹਾ ਹੈ।"
            return text

        elif lang_key == "od-IN":
            origin_badge = "ସରକାରୀ ଉତ୍ସ • ସର୍ବଶେଷ ଦୈନିକ ତଥ୍ୟ" if origin == "production_live" else "ସରକାରୀ ଉତ୍ସ • ସଂରକ୍ଷିତ ତଥ୍ୟ"
            text = (
                f"ଯାଞ୍ଚ ହୋଇଥିବା ମଣ୍ଡି ଦର: {market} ମଣ୍ଡିରେ {commodity} ({district}, {state})।\n"
                f"- ଫସଲ: {commodity}\n"
                f"- ମଣ୍ଡି: {market} ({district}, {state})\n"
                f"- କିସମ / ଗ୍ରେଡ୍: {vg_str}\n"
                f"- ସର୍ବନିମ୍ନ ଦର: ₹{min_p:.2f}/କ୍ୱିଣ୍ଟାଲ\n"
                f"- ସର୍ବାଧିକ ଦର: ₹{max_p:.2f}/କ୍ୱିଣ୍ଟାଲ\n"
                f"- ମଡେଲ୍ ଦର: ₹{modal_p:.2f}/କ୍ୱିଣ୍ଟାଲ\n"
                f"- ଆଗମନ ତାରିଖ: {arrival_date}\n"
                f"- ଉତ୍ସ: {source}\n"
                f"- ତଥ୍ୟ ସ୍ଥିତି: {origin} ({origin_badge})"
            )
            if has_tomorrow:
                text += "\n- ଟିପ୍ପଣୀ: ଆସନ୍ତାକାଲିର ସରକାରୀ ବଜାର ଦର ପୂର୍ବରୁ ପ୍ରକାଶିତ ହୁଏ ନାହିଁ। ସର୍ବଶେଷ ଯାଞ୍ଚ ହୋଇଥିବା ଦୈନିକ ଆଗମନ ତଥ୍ୟ ପ୍ରଦର୍ଶିତ ହେଉଛି।"
            return text

        # Default: en-IN
        origin_badge = "Official source • Latest available daily data" if origin == "production_live" else "Official source • Cached data"
        raw_answer = (
            f"Verified Market Price: {commodity} in {market} Mandi ({district}, {state}).\n"
            f"- Commodity: {commodity}\n"
            f"- Market: {market} ({district}, {state})\n"
            f"- Variety / Grade: {vg_str}\n"
            f"- Minimum Price: ₹{min_p:.2f}/quintal\n"
            f"- Maximum Price: ₹{max_p:.2f}/quintal\n"
            f"- Modal Price: ₹{modal_p:.2f}/quintal\n"
            f"- Arrival Date: {arrival_date}\n"
            f"- Source: {source}\n"
            f"- Data Origin: {origin} ({origin_badge})"
        )
        if has_tomorrow:
            raw_answer += "\n- Note: Tomorrow's official prices are not published in advance. Displaying the latest verified daily arrival data."
        return raw_answer

    def _format_scheme_response(self, top_scheme: EvidenceItemDTO, language: str) -> str:
        """Formats structured government scheme evidence into regional language text."""
        lang_key = language if language != "or-IN" else "od-IN"

        if lang_key == "hi-IN":
            return (
                f"आधिकारिक सरकारी योजना: {top_scheme.title}\n"
                f"- प्रायोजक एजेंसी: {top_scheme.issuing_authority}\n\n"
                f"{top_scheme.content}\n\n"
                f"पात्रता संबंधी नोट: आधिकारिक दस्तावेज में उल्लिखित पात्रता मानदंड ऊपर दिए गए हैं। आधिकारिक पोर्टल ({top_scheme.official_url}) पर आपके भूमि रिकॉर्ड और दस्तावेजों के सत्यापन के बिना व्यक्तिगत पात्रता निर्धारित नहीं की जा सकती है।"
            )
        elif lang_key == "ta-IN":
            return (
                f"அதிகாரப்பூர்வ அரசுத் திட்டம்: {top_scheme.title}\n"
                f"- வழங்கும் முகமை: {top_scheme.issuing_authority}\n\n"
                f"{top_scheme.content}\n\n"
                f"தகுதி குறித்த குறிப்பு: ஆவணப்படுத்தப்பட்ட தகுதி அளவுகோல்கள் மேலே பட்டியலிடப்பட்டுள்ளன. அதிகாரப்பூர்வ போர்ட்டலில் ({top_scheme.official_url}) உங்கள் நில ஆவணங்கள் மற்றும் ஆவணங்களை சரிபார்க்காமல் தனிப்பட்ட விவசாயி தகுதியை தீர்மானிக்க முடியாது."
            )
        elif lang_key == "te-IN":
            return (
                f"అధికారిక ప్రభుత్వ పథకం: {top_scheme.title}\n"
                f"- స్పాన్సరింగ్ ఏజెన్సీ: {top_scheme.issuing_authority}\n\n"
                f"{top_scheme.content}\n\n"
                f"అర్హతపై గమనిక: పైన పేర్కొన్న అర్హతా ప్రమాణాలు అధికారిక పత్రాల ప్రకారం ఉన్నాయి. అధికారిక పోర్టల్ ({top_scheme.official_url}) వద్ద మీ భూమి రికార్డులు ధృవీకరించకుండా వ్యక్తిగత అర్హతను నిర్ణయించలేము."
            )
        elif lang_key == "mr-IN":
            return (
                f"अधिकृत शासकीय योजना: {top_scheme.title}\n"
                f"- प्रायोजक संस्था: {top_scheme.issuing_authority}\n\n"
                f"{top_scheme.content}\n\n"
                f"पात्रतेबाबत टीप: अधिकृत कागदपत्रातील निकष वर नमूद केले आहेत. अधिकृत पोर्टलवर ({top_scheme.official_url}) आपल्या जमिनीच्या नोंदींची पडताळणी केल्याशिवाय वैयक्तिक पात्रता निश्चित केली जाऊ शकत नाही."
            )

        # Default en-IN
        return (
            f"Official Government Scheme: {top_scheme.title}\n"
            f"- Sponsoring Agency: {top_scheme.issuing_authority}\n\n"
            f"{top_scheme.content}\n\n"
            f"Note on Eligibility: Documented eligibility criteria are listed above. Individual farmer eligibility cannot be determined without verifying your specific land records and documentation at the official portal ({top_scheme.official_url})."
        )

    def _persist_log(
        self,
        db: Session,
        response: AdvisorQueryResponse,
        preprocessed,
        conv_id: str,
        start_time: float,
        current_user: Optional[Any] = None,
    ):
        """Safely logs query and response to database without breaking on DB lock/absence."""
        try:
            latency_ms = int((time.time() - start_time) * 1000)

            # Determine farmer profile (authenticated user vs guest)
            if current_user and getattr(current_user, "id", None):
                session_key = f"user-{current_user.id}"
                farmer = db.query(FarmerProfile).filter(FarmerProfile.session_id == session_key).first()
                if not farmer:
                    farmer = FarmerProfile(
                        id=str(uuid.uuid4()),
                        session_id=session_key,
                        full_name=getattr(current_user, "full_name", None) or getattr(current_user, "email", "Farmer"),
                        preferred_language=response.language,
                        state="All-India",
                        district="General",
                    )
                    db.add(farmer)
                    db.flush()
            else:
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
            else:
                conv.updated_at = datetime.now(timezone.utc)

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
            logger.error(f"Failed to persist query/response log to database: {str(e)}", exc_info=True)
            db.rollback()
            raise


advisor_orchestrator = AdvisorOrchestrator()
