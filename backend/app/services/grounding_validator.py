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
        "bn-IN": "এই প্রশ্নের নিরাপদ উত্তর দেওয়ার জন্য আনুষ্ঠানিক কৃষি এবং সরকারি সূত্রে পর্যাপ্ত যাচাইকৃত তথ্য পাওয়া যায়নি।",
        "gu-IN": "આ પ્રશ્નનો સુરક્ષિત જવાબ આપવા માટે સત્તાવાર કૃષિ અને સરકારી સ્ત્રોતોમાં પૂરતી ચકાસાયેલ માહિતી મળી નથી.",
        "ml-IN": "ഈ ചോദ്യത്തിന് സുരക്ഷിതമായ ഉത്തരം നൽകുന്നതിന് ഔദ്യോഗിക കാർഷിക, സർക്കാർ സ്രോതസ്സുകളിൽ ആവശ്യത്തിന് സ്ഥിരീകരിച്ച വിവരങ്ങൾ ലഭ്യമല്ല.",
        "pa-IN": "ਇਸ ਸਵਾਲ ਦਾ ਸੁਰੱਖਿਅਤ ਜਵਾਬ ਦੇਣ ਲਈ ਅਧਿਕਾਰਤ ਖੇਤੀਬਾੜੀ ਅਤੇ ਸਰਕਾਰੀ ਸਰੋਤਾਂ ਵਿੱਚ ਲੋੜੀਂਦੀ ਤਸਦੀਕਸ਼ੁਦਾ ਜਾਣਕਾਰੀ ਨਹੀਂ ਮਿਲੀ।",
        "od-IN": "ଏହି ପ୍ରଶ୍ନର ନିରାପଦ ଉତ୍ତର ଦେବା ପାଇଁ ସରକାରୀ ଏବଂ କୃଷି ଉତ୍ସରୁ ଯଥେଷ୍ଟ ଯାଞ୍ଚ ହୋଇଥିବା ତଥ୍ୟ ମିଳିଲା ନାହିଁ।",
        "en-IN": "I couldn't find enough verified agricultural information in official ICAR, SAU, or government sources to answer that safely.",
    }

    WEATHER_ABSTENTION_MESSAGES = {
        "hi-IN": "ओपन-मेटियो मौसम सेवा वर्तमान में अनुपलब्ध है। कृपया कुछ समय बाद पुनः प्रयास करें।",
        "te-IN": "ఓపెన్-మెటియో వాతావరణ సేవ ప్రస్తుతం అందుబాటులో లేదు. దయచేసి కొద్దిసేపటి తర్వాత మళ్లీ ప్రయత్నించండి.",
        "ta-IN": "ஓபன்-மெட்டியோ வானிலை சேவை தற்போது கிடைக்கவில்லை. சிறிது நேரம் கழித்து மீண்டும் முயற்சிக்கவும்.",
        "mr-IN": "ओपन-मेटिओ हवामान सेवा सध्या उपलब्ध नाही. कृपया थोड्या वेळाने पुन्हा प्रयत्न करा.",
        "kn-IN": "ಓಪನ್-ಮೆಟಿಯೊ ಹವಾಮಾನ ಸೇವೆ ಪ್ರಸ್ತುತ ಲಭ್ಯವಿಲ್ಲ. ದಯವಿಟ್ಟು ಸ್ವಲ್ಪ ಸಮಯದ ನಂತರ ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.",
        "bn-IN": "ওপেন-মেটিও আবহাওয়া পরিষেবা বর্তমানে অনুপলব্ধ। অনুগ্রহ করে কিছুক্ষণ পরে আবার চেষ্টা করুন।",
        "gu-IN": "ઓપન-મેટિઓ હવામાન સેવા હાલમાં અનુપલબ્ધ છે. કૃપા કરીને થોડા સમય પછી ફરી પ્રયાસ કરો.",
        "ml-IN": "ഓപ്പൺ-മെറ്റിയോ കാലാവസ്ഥാ സേവനം ഇപ്പോൾ ലഭ്യമല്ല. ദയവായി അല്പം കഴിഞ്ഞ് വീണ്ടും ശ്രമിക്കുക.",
        "pa-IN": "ਓਪਨ-ਮੇਟੀਓ ਮੌਸਮ ਸੇਵਾ ਫਿਲਹਾਲ ਉਪਲਬਧ ਨਹੀਂ ਹੈ। ਕਿਰਪਾ ਕਰਕੇ ਕੁਝ ਸਮੇਂ ਬਾਅਦ ਦੁਬਾਰਾ ਕੋਸ਼ਿਸ਼ ਕਰੋ।",
        "od-IN": "ଓପନ୍-ମେଟିଓ ପାଣିପାଗ ସେବା ବର୍ତ୍ତମାନ ଉପଲବ୍ଧ ନାହିଁ। ଦୟାକରି କିଛି ସମୟ ପରେ ପୁନର୍ବାର ଚେଷ୍ଟା କରନ୍ତୁ।",
        "en-IN": "The Open-Meteo weather service is temporarily unavailable. Please try again shortly.",
    }

    def get_abstention_text(self, language: str = "en-IN", reason_detail: Optional[str] = None, is_weather: bool = False) -> str:
        lang_key = language
        if lang_key == "or-IN":
            lang_key = "od-IN"
        if is_weather:
            base = self.WEATHER_ABSTENTION_MESSAGES.get(lang_key, self.WEATHER_ABSTENTION_MESSAGES["en-IN"])
            if reason_detail and language == "en-IN":
                return f"{base} ({reason_detail})"
            return base
        base = self.DEFAULT_ABSTENTION_MESSAGES.get(lang_key, self.DEFAULT_ABSTENTION_MESSAGES["en-IN"])
        if reason_detail and language == "en-IN":
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

        # 5. Check for dedicated weather intents
        if intent in (
            AgriculturalIntent.WEATHER_CURRENT,
            AgriculturalIntent.WEATHER_FORECAST,
            AgriculturalIntent.WEATHER_RAIN,
            AgriculturalIntent.WEATHER_TEMPERATURE,
            AgriculturalIntent.WEATHER_ADVISORY,
        ):
            valid_weather = [
                e for e in evidence
                if e.source_name == "Open-Meteo" and e.data_origin in ("production_live", "production_cached")
            ]
            if not valid_weather:
                return False, "Open-Meteo weather service data is currently unavailable."
            return True, None

        # 6. Check agricultural knowledge chunks (Crop Advisory, Pest/Disease, General Agri)
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
