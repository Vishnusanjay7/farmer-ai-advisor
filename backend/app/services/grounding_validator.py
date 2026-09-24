import re
from typing import List, Tuple, Optional
from backend.app.core.logging import logger
from backend.app.schemas.advisor import AgriculturalIntent, EvidenceItemDTO


class GroundingValidator:
    """
    Two-stage grounding validation safety layer:
    1. Pre-LLM evidence validation: Validates sufficiency, relevance, and authoritative origin.
       Triggers immediate safe abstention if evidence is insufficient or unsupported.
    2. Post-LLM generation safety heuristic: Checks that numbers, dosages, citations,
       and data origins strictly adhere to retrieved evidence without hallucination.
    """

    DEFAULT_ABSTENTION_MESSAGES = {
        "hi-IN": "मुझे इस सवाल का सुरक्षित उत्तर देने के लिए आधिकारिक कृषि और सरकारी स्रोतों में पर्याप्त सत्यापित जानकारी नहीं मिली।",
        "te-IN": "ఈ ప్రశ్నకు సురక్షితమైన సమాధానం ఇవ్వడానికి అధికారిక వ్యవసాయ మరియు ప్రభుత్వ వనరులలో తగినంత ధృవీకరించబడిన సమాచారం లభించలేదు.",
        "ta-IN": "இந்தக் கேள்விக்கு பாதுகாப்பான பதிலளிக்க அதிகாரப்பூர்வ வேளாண் மற்றும் அரசு ஆதாரங்களில் போதுமான சரிபார்க்கப்பட்ட தகவல் கிடைக்கவில்லை.",
        "mr-IN": "या प्रश्नाचे सुरक्षित उत्तर देण्यासाठी अधिकृत कृषी आणि शासकीय स्त्रोतांमध्ये पुरेशी पडताळणी केलेली माहिती मिळाली नाही.",
        "kn-IN": "ಈ ಪ್ರಶ್ನೆಗೆ ಸುರಕ್ಷಿತ ಉತ್ತರಿಸಲು ಅಧಿಕೃತ ಕೃಷಿ ಮತ್ತು ಸರ್ಕಾರಿ ಮೂಲಗಳಲ್ಲಿ ಸಾಕಷ್ಟು ಪರಿಶೀಲಿಸಿದ ಮಾಹಿತಿ ಲಭ್ಯವಿಲ್ಲ.",
        "en-IN": "I couldn't find enough verified agricultural information in official ICAR, SAU, or government sources to answer that safely.",
    }

    def get_abstention_text(self, language: str = "en-IN", reason_detail: Optional[str] = None) -> str:
        base = self.DEFAULT_ABSTENTION_MESSAGES.get(language, self.DEFAULT_ABSTENTION_MESSAGES["en-IN"])
        if reason_detail:
            return f"{base} ({reason_detail})"
        return base

    def validate_pre_llm(
        self,
        intent: AgriculturalIntent,
        evidence: List[EvidenceItemDTO],
        similarity_threshold: float = 0.55,
        language: str = "en-IN",
    ) -> Tuple[bool, Optional[str]]:
        """
        Validates if evidence is sufficient to call the LLM.
        Returns: (is_sufficient: bool, abstention_reason: Optional[str])
        """
        # 1. Unsupported or unknown intent must immediately abstain
        if intent in (AgriculturalIntent.UNSUPPORTED, AgriculturalIntent.UNKNOWN):
            return False, "Query is outside the supported agricultural advisory scope."

        # 2. Check for empty evidence
        if not evidence:
            return False, "No verified official agricultural records matched the query."

        # 3. Check for mandi price safety
        if intent == AgriculturalIntent.MANDI_PRICE:
            # Mandi evidence must have at least one authoritative production record
            valid_mandi = [
                e for e in evidence
                if e.data_origin in ("production_live", "production_cached") and e.status == "authoritative"
            ]
            if not valid_mandi:
                return False, "No verified live or cached market prices found for the specified market or commodity. Development mock data cannot be used."
            return True, None

        # 4. Check for government schemes
        if intent == AgriculturalIntent.GOVERNMENT_SCHEME:
            valid_schemes = [e for e in evidence if e.relevance_score >= 0.50]
            if not valid_schemes:
                return False, "No matching central or state government agricultural schemes were found."
            return True, None

        # 5. Check agricultural knowledge chunks (Crop Advisory, Pest/Disease, General Agri)
        authoritative_items = [
            e for e in evidence
            if e.relevance_score >= similarity_threshold and e.status == "authoritative"
        ]
        if not authoritative_items:
            return False, f"Retrieved knowledge relevance is below the safety threshold ({similarity_threshold})."

        return True, None

    def validate_post_llm(
        self,
        generated_text: str,
        evidence: List[EvidenceItemDTO],
        intent: AgriculturalIntent,
    ) -> Tuple[bool, Optional[str]]:
        """
        Post-generation safety heuristic.
        Checks for:
        - Non-empty output.
        - Unsupported numeric chemical dosages.
        - Claiming development data is live government data.
        Returns: (is_valid: bool, fallback_reason: Optional[str])
        """
        if not generated_text or not generated_text.strip():
            return False, "LLM returned an empty response."

        combined_evidence_text = " ".join([e.content for e in evidence]).lower()

        # Check for chemical dosages / numbers in generated text
        # Regex for dosages: e.g. 2.5 ml, 500 g, 20 kg/ha
        dosage_patterns = re.findall(r"\b\d+(?:\.\d+)?\s*(?:ml|g|kg|litre|liter|gm|ppm|%)\b", generated_text.lower())
        for dosage in dosage_patterns:
            num_part = re.search(r"\d+(?:\.\d+)?", dosage).group(0)
            if num_part not in combined_evidence_text:
                logger.warning(f"Post-LLM Safety Triggered: Unverified dosage '{dosage}' found in LLM output")
                return False, f"Generated response contained unverified chemical dosage ({dosage}) not found in official source documents."

        # Check for price figures in MANDI_PRICE queries
        if intent == AgriculturalIntent.MANDI_PRICE:
            price_mentions = re.findall(r"(?:rs\.?|₹|inr)\s*(\d{2,6})", generated_text.lower())
            for p in price_mentions:
                if p not in combined_evidence_text:
                    logger.warning(f"Post-LLM Safety Triggered: Price '{p}' not found in retrieved mandi evidence")
                    return False, f"Generated response contained an unverified price figure ({p}) not present in verified market arrivals."

        # Check development data claim
        if "development" in combined_evidence_text and ("live official government" in generated_text.lower()):
            return False, "Generated text falsely presented development data as live government data."

        return True, None


grounding_validator = GroundingValidator()
