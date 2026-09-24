import re
from typing import Tuple
from backend.app.schemas.advisor import AgriculturalIntent


class IntentClassifier:
    """
    Classifies farmer queries into explicit agricultural intents with strict
    safety guardrails: ambiguous or non-agricultural queries are classified as UNSUPPORTED.
    """

    MANDI_KEYWORDS = [
        r"\bmandi\b", r"\bprice\b", r"(?<!seed\s)(?<!seeding\s)(?<!application\s)(?<!dose\s)(?<!dosage\s)\brate\b",
        r"\bbhav\b", r"\bmodal price\b",
        r"\bmarket price\b", r"\bbazaar\b", r"\bbazar\b",
        "मंडी", "भाव", "दाम", "दर", "बाजार भाव",
        "ధర", "మార్కెట్", "రేటు",
        "விலை", "சந்தை",
        "दर", "बाजारभाव"
    ]

    SCHEME_KEYWORDS = [
        r"\bpm[- ]?kisan\b", r"\bpmfby\b", r"\bkcc\b", r"\bsoil health card\b",
        r"\bpmksy\b", r"\bscheme\b", r"\byojana\b", r"\bsubsidy\b", r"\beligibility\b",
        r"\beligible\b", r"\bportal\b", r"\binsurance\b", r"\bcredit card\b",
        "योजना", "सब्सिडी", "पात्रता", "बीमा", "किसान क्रेडिट", "पीएम किसान",
        "పథకం", "సబ్సిడీ", "అర్హత",
        "திட்டம்", "மானியம்"
    ]

    PEST_DISEASE_KEYWORDS = [
        r"\bpest\b", r"\bdisease\b", r"\bborer\b", r"\bblight\b", r"\brot\b",
        r"\brust\b", r"\bwilting\b", r"\binsect\b", r"\bfungus\b", r"\bcaterpillar\b",
        r"\bworm\b", r"\binfestation\b", r"\bsymptom\b", r"\byellow stem borer\b",
        r"\bbollworm\b", r"\baphid\b", r"\bmite\b", r"\bdamage\b", r"\bcontrol\b",
        r"\bkill\b", r"\btreatment\b",
        "कीट", "रोग", "इल्ली", "तनाव", "झुलसा", "फंगस", "रोकथाम", "उपचार", "कीड़ा", "तना छेदक", "नियंत्रण", "रतुआ", "माहू", "सूंड़ी",
        "తెగులు", "పురుగు", "నివారణ",
        "பூச்சி", "நோய்", "கட்டுப்பாடு"
    ]

    CROP_ADVISORY_KEYWORDS = [
        r"\bfertilizer\b", r"\burea\b", r"\bdap\b", r"\bnpk\b", r"\birrigation\b",
        r"\birrigate\b", r"\birrigated\b", r"\bwatering\b",
        r"\bwater\b", r"\bsowing\b", r"\bseed\b", r"\bvariety\b", r"\bspacing\b",
        r"\bharvest\b", r"\byield\b", r"\bnutrient\b", r"\bdosage\b", r"\bmanure\b",
        r"\bgrowth\b", r"\bflowering\b", r"\btransplant\b",
        "खाद", "उर्वरक", "यूरिया", "बुवाई", "सिंचाई", "किस्म", "बीज", "कटाई", "पैदावार",
        "ఎరువు", "విత్తనం", "సాగు", "నీటిపారుదల",
        "உரம்", "விதை", "பாசனம்"
    ]

    GENERAL_AGRI_KEYWORDS = [
        r"\bcrop\b", r"\bfarm\b", r"\bfarming\b", r"\bagriculture\b", r"\bsoil\b",
        r"\bweather\b", r"\bmonsoon\b", r"\bseason\b", r"\bkharif\b", r"\brabi\b",
        "खेती", "कृषि", "फसल", "मिट्टी", "मौसम", "खरीफ", "रबी",
        "వ్యవసాయం", "పంట", "నేల",
        "விவசாயம்", "பயிர்", "மண்"
    ]

    OUT_OF_SCOPE_KEYWORDS = [
        r"\bcricket\b", r"\bipl\b", r"\bfootball\b", r"\bmatch\b", r"\bscore\b",
        r"\bmovie\b", r"\bcinema\b", r"\bactor\b", r"\bactress\b", r"\bsong\b",
        r"\bpolitics\b", r"\belection\b", r"\bpresident\b", r"\bprime minister\b",
        r"\bstock market\b", r"\bbitcoin\b", r"\bcrypto\b", r"\biphone\b",
        r"\blaptop\b", r"\bcomputer\b", r"\bcode\b", r"\bpython\b", r"\bhack\b",
        r"\bweather in new york\b", r"\bcar\b", r"\bbike\b"
    ]

    def classify(self, query: str) -> Tuple[AgriculturalIntent, float]:
        """
        Classifies query into AgriculturalIntent and returns (intent, confidence).
        Explicitly routes out-of-scope or ambiguous questions to UNSUPPORTED.
        """
        q_lower = query.lower()

        # Check explicit out-of-scope / non-agricultural queries first
        for pattern in self.OUT_OF_SCOPE_KEYWORDS:
            if re.search(pattern, q_lower):
                return AgriculturalIntent.UNSUPPORTED, 0.99

        # Mandi price takes high precedence if price/market terms match
        for pattern in self.MANDI_KEYWORDS:
            if re.search(pattern, q_lower):
                return AgriculturalIntent.MANDI_PRICE, 0.95

        # Government scheme check
        for pattern in self.SCHEME_KEYWORDS:
            if re.search(pattern, q_lower):
                return AgriculturalIntent.GOVERNMENT_SCHEME, 0.95

        # Pest & disease check
        pest_matches = sum(1 for p in self.PEST_DISEASE_KEYWORDS if re.search(p, q_lower))
        if pest_matches > 0:
            return AgriculturalIntent.PEST_DISEASE, min(0.70 + (pest_matches * 0.1), 0.98)

        # Crop advisory check
        crop_adv_matches = sum(1 for p in self.CROP_ADVISORY_KEYWORDS if re.search(p, q_lower))
        if crop_adv_matches > 0:
            return AgriculturalIntent.CROP_ADVISORY, min(0.70 + (crop_adv_matches * 0.1), 0.98)

        # General agriculture check
        for pattern in self.GENERAL_AGRI_KEYWORDS:
            if re.search(pattern, q_lower):
                return AgriculturalIntent.GENERAL_AGRICULTURE, 0.75

        # If no agricultural or scheme or price signal matched, do NOT guess crop or pest!
        return AgriculturalIntent.UNSUPPORTED, 0.90


intent_classifier = IntentClassifier()
