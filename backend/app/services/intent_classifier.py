import re
from typing import Tuple
from backend.app.schemas.advisor import AgriculturalIntent


class IntentClassifier:
    """
    Classifies farmer queries into explicit agricultural intents with strict
    safety guardrails: ambiguous or non-agricultural queries are classified as UNSUPPORTED.
    Supports comprehensive agricultural domains across 11 Indian regional languages.
    """

    MANDI_KEYWORDS = [
        r"\bmandi\b", r"\bprice\b", r"(?<!seed\s)(?<!seeding\s)(?<!application\s)(?<!dose\s)(?<!dosage\s)\brate\b",
        r"\bbhav\b", r"\bmodal price\b",
        r"\bmarket price\b", r"\bbazaar\b", r"\bbazar\b",
        "मंडी", "भाव", "दाम", "बाजार भाव",
        "మార్కెట్", "రేటు",
        "விலை", "சந்தை", "கோதுமை விலை",
        "बाजारभाव", "ಬೆಲೆ", "ભાવ", "നിരക്ക്", "ਭਾਅ",
        r"(?:\s|^)(?:दर|ದರ|দর|ଦର|ధర)(?:\s|$|[?.,!])"
    ]

    CROP_INSURANCE_KEYWORDS = [
        r"\bpmfby\b", r"\bfasal bima\b", r"\bcrop insurance\b", r"\bweather insurance\b",
        r"\binsurance claim\b", r"\bcrop damage compensation\b",
        "फसल बीमा", "पीएम फसल बीमा", "बीमा दावा", "मुआवजा",
        "పంటల బీమా", "పంట బీమా", "నష్టపరిహారం",
        "பயிர் காப்பீடு", "பயிர் இழப்பீடு",
        "पीक विमा", "विमा दावा", "ಬೆಳೆ ವಿಮೆ", "ಫಸಲ್ ಬಿಮಾ", "ফসল বীমা", "પાક વીમો", "വിള ഇൻഷുറൻസ്", "ਫਸਲੀ ਬੀਮਾ", "ଫସଲ ବୀମା"
    ]

    CREDIT_KEYWORDS = [
        r"\bkcc\b", r"\bkisan credit\b", r"\bcrop loan\b", r"\bagri loan\b", r"\bfarm loan\b",
        r"\bcredit card\b", r"\binterest subvention\b", r"\bnabard loan\b",
        "किसान क्रेडिट", "केसीसी", "कृषि ऋण", "फसल ऋण", "कृषि लोन", "ब्याज छूट",
        "కిసాన్ క్రెడిట్", "వ్యవసాయ రుణం", "పంట రుణం",
        "விவசாயக் கடன்", "பயிர் கடன்", "கிசான் கிரெடிட்",
        "पीक कर्ज", "कृषी कर्ज", "ಕೃಷಿ ಸಾಲ", "কৃষি ঋণ", "ખેતી ધિരാણ", "കാർഷിക വായ്പ", "ਖੇਤੀ ਕਰਜ਼ਾ", "କୃଷି ଋଣ"
    ]

    SCHEME_KEYWORDS = [
        r"\bpm[- ]?kisan\b", r"\bsoil health card\b",
        r"\bpmksy\b", r"\bscheme\b", r"\byojana\b", r"\bsubsidy\b", r"\beligibility\b",
        r"\beligible\b", r"\bportal\b",
        "योजना", "सब्सिडी", "पात्रता", "पीएम किसान", "सरकारी योजना",
        "పథకం", "సబ్సిడీ", "అర్హత",
        "திட்டம்", "மானியம்",
        "शासकीय योजना", "ಯೋಜನೆ", "ಅನುದಾನ", "যোজನಾ", "સબસિડી", "പദ്ധതി", "ਸਕੀਮ", "ଯୋଜନା"
    ]

    SEED_TREATMENT_KEYWORDS = [
        r"\bseed treatment\b", r"\bbeej upchar\b", r"\bbeej sanskar\b", r"\bseed priming\b",
        r"\btreating seed\b", r"\bseed dressing\b",
        "बीज उपचार", "बीजोपचार", "बीज संस्कार",
        "విత్తన శుద్ధి", "విత్తన చికిత్స",
        "விதை நேர்த்தி", "விதை சிகிச்சை",
        "बीज प्रक्रिया", "ಬೀಜೋಪಚಾರ", "বীজ শোধন", "બીજ માવજત", "വിത്തു പരിചരണം", "ਬੀਜ ਸੋਧ", "ବିହନ ବିଶୋଧନ"
    ]

    SEED_SELECTION_KEYWORDS = [
        r"\bseed selection\b", r"\bwhich seeds?\b", r"\bbest seeds?\b", r"\bcertified seeds?\b",
        r"\bhybrid seeds?\b", r"\bseed rate\b", r"\bseed quality\b", r"\bselect\b.*\bseeds?\b",
        r"\bchoose\b.*\bseeds?\b",
        "बीज चयन", "उत्तम बीज", "प्रमाणित बीज", "संकर बीज", "बीज दर",
        "విత్తన ఎంపిక", "మేలైన విత్తనాలు", "హైబ్రిడ్ విత్తనాలు",
        "விதை தேர்வு", "சிறந்த விதை", "வீரிய விதை",
        "बियाणे निवड", "ಬೀಜ ಆಯ್ಕೆ", "বীজ নির্বাচন", "બિયારણ પસંદગી", "വിത്തു തിരഞ്ഞെടുപ്പ്", "ਬੀਜ ਦੀ ਚੋਣ", "ବିହନ ଚୟନ"
    ]

    SOIL_MANAGEMENT_KEYWORDS = [
        r"\bsoil management\b", r"\bsoil testing\b", r"\bsoil health\b", r"\bsoil fertility\b",
        r"\bacidic soil\b", r"\balkaline soil\b", r"\bsaline soil\b", r"\bsoil ph\b",
        "मिट्टी की जांच", "मृदा स्वास्थ्य", "मृदा परीक्षण", "मिट्टी सुधार", "भूमि सुधार",
        "నేల యాజమాన్యం", "భూసార పరీక్ష", "మట్టి పరీక్ష",
        "மண் மேலாண்மை", "மண் பரிசோதனை", "மண் வளம்",
        "माती परीक्षण", "ಮಣ್ಣು ಪರೀಕ್ಷೆ", "মাটি পরীক্ষা", "જમીન ચકાસણી", "മണ്ണ് പരിശോധന", "ਮਿੱਟੀ ਦੀ ਪਰਖ", "ମୃତ୍ତିକା ପରୀକ୍ଷା"
    ]

    WEED_MANAGEMENT_KEYWORDS = [
        r"\bweed\b", r"\bweeds\b", r"\bweed control\b", r"\bweed management\b",
        r"\bherbicide\b", r"\bweedicide\b", r"\bglyphosate\b", r"\bde-weeding\b",
        "खरपतवार", "निराई गुड़ाई", "शाकनाशी", "खरपतवार नियंत्रण", "घास फूस",
        "కలుపు", "కలుపు నివారణ", "కలుపు మందు",
        "களை", "களை கட்டுப்பாடு", "களைக்கொல்லி",
        "तण", "तण नियंत्रण", "तणनाशक", "ಕಳೆ", "ಕಳೆ ನಿರ್ವಹಣೆ", "আগাছা", "નિંદામણ", "കള", "ਨਦੀਨ", "ତୃଣ ନିୟନ୍ତ୍ରଣ"
    ]

    STORAGE_KEYWORDS = [
        r"\bstorage\b", r"\bgrain storage\b", r"\bwarehouse\b", r"\bsilo\b",
        r"\bcold storage\b", r"\bweevil\b", r"\bstorage pest\b", r"\bstore grain\b",
        "भंडारण", "गोदाम", "अनाज भंडारण", "शीतगृह", "कोल्ड स्टोरेज",
        "నిల్వ", "గిడ్డంగి", "కోల్డ్ స్టోరేజ్", "ధాన్యం నిల్వ",
        "சேமிப்பு", "தானிய சேமிப்பு", "கிடங்கு", "குளிர்சாதன கிடங்கு",
        "साठवणूक", "दाಸ್ತಾನು", "গুদাম", "સંગ્રહ", "സംഭരണം", "ਭੰਡਾਰਨ", "ସଂରକ୍ଷଣ"
    ]

    POST_HARVEST_KEYWORDS = [
        r"\bpost harvest\b", r"\bcuring\b", r"\bdrying\b", r"\bsorting\b",
        r"\bgrading\b", r"\bprocessing\b", r"\bvalue addition\b",
        "कटाई उपरांत", "सुखाना", "छंटाई", "ग्रेडिंग", "प्रसंस्करण",
        "కోత తదనంతర", "ఆరబెట్టడం", "గ్రేడింగ్",
        "அறுவடைக்கு பின்", "உலர்த்துதல்", "தரம் பிரித்தல்",
        "कापणीपश्चात", "ಕೊಯ್ಲಿನ ನಂತರ", "ফসল কাটার পর", "કાપણી પછીની પ્રક્રિયા", "വിളവെടുപ്പാനന്തര സൂക്ഷിപ്പ്", "ଅମଳ ପରବର୍ତ୍ତୀ ଯତ୍ନ"
    ]

    HARVESTING_KEYWORDS = [
        r"\bharvesting\b", r"\bharvest time\b", r"\bcutting time\b", r"\bmaturity stage\b",
        r"\breaping\b", r"\bthreshing\b", r"\bcombine harvester\b", r"\bwhen to harvest\b",
        "कटाई", "फसल की कटाई", "गहाई", "कटाई का समय",
        "కోత", "పంట కోత", "కోత సమయం",
        "அறுவடை", "அறுவடை காலம்",
        "कापणी", "मळणी", "ಕೊಯ್ಲು", "ফসল কাটা", "કાપણી", "വിളവെടുപ്പ്", "ਵਾਢੀ", "ଅମଳ"
    ]

    IRRIGATION_KEYWORDS = [
        r"\birrigation\b", r"\birrigate\b", r"\birrigated\b", r"\bwatering\b",
        r"\bdrip irrigation\b", r"\bsprinkler\b", r"\bwater requirement\b", r"\bflood irrigation\b",
        "सिंचाई", "पानी देना", "ड्रिप", "स्प्रिंकलर", "फव्वारा", "जल प्रबंधन",
        "నీటిపారుదల", "నీరు పెట్టడం", "డ్రిప్", "స్ప్రింక్లర్",
        "பாசனம்", "நீர்ப்பாசனம்", "சொட்டு நீர்", "தெளிப்பு நீர்",
        "सिंचन", "पाणी व्यवस्थापन", "ठिबक सिंचन", "ನೀರಾವರಿ", "সেচ", "પિયત", "ജലസேചനം", "ਸਿੰਚਾਈ", "ଜଳସେଚନ"
    ]

    FERTILIZER_KEYWORDS = [
        r"\bfertilizer\b", r"\bfertiliser\b", r"\burea\b", r"\bdap\b", r"\bnpk\b",
        r"\bpotash\b", r"\bmanure\b", r"\bcompost\b", r"\bmicronutrient\b", r"\bzinc application\b",
        "खाद", "उर्वरक", "यूरिया", "डीएपी", "एनपीके", "पोटाश", "गोबर खाद", "कंपोस्ट",
        "ఎరువు", "ఎరువులు", "యూరియా", "డిఎపి",
        "உரம்", "உரங்கள்", "யூரியா", "டிஏபி", "சாணம்",
        "खत", "खते", "युरिया", "ಗೊಬ್ಬರ", "সার", "ખાતર", "വളം", "ਖਾਦ", "ସାର"
    ]

    PEST_DISEASE_KEYWORDS = [
        r"\bpest\b", r"\bdisease\b", r"\bborer\b", r"\bblight\b", r"\brot\b",
        r"\brust\b", r"\bwilting\b", r"\binsect\b", r"\bfungus\b", r"\bcaterpillar\b",
        r"\bworm\b", r"\binfestation\b", r"\bsymptom\b", r"\byellow stem borer\b",
        r"\bbollworm\b", r"\baphid\b", r"\bmite\b", r"\bdamage\b", r"\bcontrol\b",
        r"\bkill\b", r"\btreatment\b",
        "कीट", "रोग", "इल्ली", "तनाव", "झुलसा", "फंगस", "रोकथाम", "उपचार", "कीड़ा", "तना छेदक", "नियंत्रण", "रतुआ", "माहू", "सूंड़ी",
        "తెగులు", "పురుగు", "నివారణ",
        "பூச்சி", "நோய்", "கட்டுப்பாடு",
        "रोग आणि कीड", "ರೋಗ", "কীটপতঙ্গ", "જીવાત", "കീടങ്ങൾ", "ਕੀੜੇ", "ରୋଗ"
    ]

    CROP_ADVISORY_KEYWORDS = [
        r"\bsowing\b", r"\bseed\b", r"\bvariety\b", r"\bspacing\b",
        r"\bharvest\b", r"\byield\b", r"\bnutrient\b", r"\bdosage\b",
        r"\bgrowth\b", r"\bflowering\b", r"\btransplant\b",
        "बुवाई", "किस्म", "बीज", "कटाई", "पैदावार",
        "విత్తనం", "సాగు",
        "விதை", "வகை",
        "लागवड", "ಬಿತ್ತನೆ", "বপন", "વાવણી", "വിത്ത്", "ਬਿਜਾਈ", "ବୁଣା"
    ]

    GENERAL_AGRI_KEYWORDS = [
        r"\bcrop\b", r"\bfarm\b", r"\bfarming\b", r"\bagriculture\b", r"\bsoil\b",
        r"\bweather\b", r"\bmonsoon\b", r"\bseason\b", r"\bkharif\b", r"\brabi\b",
        "खेती", "कृषि", "फसल", "मिट्टी", "मौसम", "खरीफ", "रबी",
        "వ్యవసాయం", "పంట", "నేల",
        "விவசாயம்", "பயிர்", "மண்",
        "शेती", "ಕೃಷಿ", "কৃষি", "ખેતી", "കൃഷി", "ਖੇਤੀ", "କୃଷି"
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

        # 1. Check explicit out-of-scope / non-agricultural queries first
        for pattern in self.OUT_OF_SCOPE_KEYWORDS:
            if re.search(pattern, q_lower):
                return AgriculturalIntent.UNSUPPORTED, 0.99

        # 2. Mandi price takes high precedence if price/market terms match
        for pattern in self.MANDI_KEYWORDS:
            if re.search(pattern, q_lower):
                return AgriculturalIntent.MANDI_PRICE, 0.95

        # 3. Government Scheme Sub-domains
        for pattern in self.CROP_INSURANCE_KEYWORDS:
            if re.search(pattern, q_lower):
                return AgriculturalIntent.CROP_INSURANCE, 0.95

        for pattern in self.CREDIT_KEYWORDS:
            if re.search(pattern, q_lower):
                return AgriculturalIntent.AGRICULTURAL_CREDIT, 0.95

        for pattern in self.SCHEME_KEYWORDS:
            if re.search(pattern, q_lower):
                return AgriculturalIntent.GOVERNMENT_SCHEME, 0.95

        # 4. Specific Agronomic Operations
        for pattern in self.SEED_TREATMENT_KEYWORDS:
            if re.search(pattern, q_lower):
                return AgriculturalIntent.SEED_TREATMENT, 0.95

        for pattern in self.SEED_SELECTION_KEYWORDS:
            if re.search(pattern, q_lower):
                return AgriculturalIntent.SEED_SELECTION, 0.95

        for pattern in self.WEED_MANAGEMENT_KEYWORDS:
            if re.search(pattern, q_lower):
                return AgriculturalIntent.WEED_MANAGEMENT, 0.95

        for pattern in self.SOIL_MANAGEMENT_KEYWORDS:
            if re.search(pattern, q_lower):
                return AgriculturalIntent.SOIL_MANAGEMENT, 0.95

        # 5. Pest & Disease check
        pest_matches = sum(1 for p in self.PEST_DISEASE_KEYWORDS if re.search(p, q_lower))
        if pest_matches > 0:
            return AgriculturalIntent.PEST_DISEASE, min(0.70 + (pest_matches * 0.1), 0.98)

        # 6. Specific Agricultural Practices
        # Preserve general crop advisory compatibility for recommended dosage inquiries
        if re.search(r"\brecommended\b.*\bdosage\b", q_lower) or re.search(r"\bdosage\b.*\brecommended\b", q_lower):
            return AgriculturalIntent.CROP_ADVISORY, 0.90

        for pattern in self.STORAGE_KEYWORDS:
            if re.search(pattern, q_lower):
                return AgriculturalIntent.STORAGE, 0.92

        for pattern in self.POST_HARVEST_KEYWORDS:
            if re.search(pattern, q_lower):
                return AgriculturalIntent.POST_HARVEST, 0.92

        for pattern in self.HARVESTING_KEYWORDS:
            if re.search(pattern, q_lower):
                return AgriculturalIntent.HARVESTING, 0.92

        for pattern in self.IRRIGATION_KEYWORDS:
            if re.search(pattern, q_lower):
                return AgriculturalIntent.IRRIGATION, 0.92

        for pattern in self.FERTILIZER_KEYWORDS:
            if re.search(pattern, q_lower):
                return AgriculturalIntent.FERTILIZER, 0.92

        # 6. Broader Crop Advisory check
        crop_adv_matches = sum(1 for p in self.CROP_ADVISORY_KEYWORDS if re.search(p, q_lower))
        if crop_adv_matches > 0:
            return AgriculturalIntent.CROP_ADVISORY, min(0.70 + (crop_adv_matches * 0.1), 0.98)

        # 7. General Agriculture check
        for pattern in self.GENERAL_AGRI_KEYWORDS:
            if re.search(pattern, q_lower):
                return AgriculturalIntent.GENERAL_AGRICULTURE, 0.75

        # 8. Ambiguous or unsupported query safely abstains
        return AgriculturalIntent.UNSUPPORTED, 0.90


intent_classifier = IntentClassifier()
