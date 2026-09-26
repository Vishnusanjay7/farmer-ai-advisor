import re
from typing import Optional, Dict, Any
from backend.app.schemas.advisor import FarmerContextDTO


class ContextExtractor:
    """
    Extracts agricultural context strictly when explicitly mentioned in the query.
    Never hallucinates or guesses unmentioned entities.
    Applies context-aware precedence rules between current query and inherited context.
    """

    CROPS = {
        "paddy": ["paddy", "rice", "धान", "चावल", "వరి", "நெல்", "भात", "ಅಕ್ಕಿ", "ಭತ್ತ", "ধান", "ચોખા", "ડાંગર", "നെല്ല്", "ਚੌਲ", "ଧାନ"],
        "wheat": ["wheat", "गेहूं", "गेंहू", "గోధుమ", "கோதுமை", "गहू", "ಗೋಧಿ", "গম", "ઘઉં", "ഗോതമ്പ്", "ਕਣਕ", "ଗହମ"],
        "cotton": ["cotton", "कपास", "पत्ती", "பருத்தி", "कापूस", "ప్రత్తి", "ಹತ್ತಿ", "তুলা", "કપાસ", "പരുത്തി", "ਕਪਾਹ", "କପା"],
        "chili": ["chili", "chilli", "mirchi", "मिर्च", "మిరప", "மிளகாய்", "मिरची", "ಮೆಣಸಿನಕಾಯಿ", "লঙ্কা", "મરચાં", "മുളക്", "ਮਿਰਚ", "ଲଙ୍କା"],
        "soybean": ["soybean", "soyabean", "सोयाबीन", "సోయాబీన్", "சோயாபீன்", "ಸೋಯಾಬೀನ್"],
        "maize": ["maize", "corn", "मक्का", "మొక్కజొన్న", "மக்காச்சோளம்", "ಮಕ್ಕೆಜೋಳ", "ভুট্টা", "મકાઈ", "ചോളം", "ਮੱਕੀ", "ମକା"],
        "sugarcane": ["sugarcane", "गन्ना", "చెరకు", "கரும்பு", "ऊस", "ಕಬ್ಬು", "আখ", "શેરડી", "കരിമ്പ്", "ਗੰਨਾ", "ଆଖୁ"],
        "mustard": ["mustard", "सरसों", "ఆవాలు", "கடுகு", "मोहरी", "ಸಾಸಿವೆ", "সরিষা", "રાઈ", "കടുക്", "ਸਰ੍ਹੋਂ", "ଶୋରିଷ"],
        "gram": ["gram", "chana", "चना", "శనగలు", "கொண்டைக்கடலை", "हरभरा", "ಕಡಲೆ", "ছোলা", "ચણા", "കടല", "ਛੋਲੇ", "ବୁଟ"],
        "dragon fruit": ["dragon fruit", "pitaya", "ड्रैगन फ्रूट", "कमलम"],
        # High-volume mandi vegetables and fruits — missing entries caused
        # explicit query crop to be silently discarded, falling back to stale
        # inherited context (e.g., tomato query returning Wheat).
        "tomato": ["tomato", "टमाटर", "టొమాటో", "தக்காளி", "tamatar", "टोमॅटो", "ಟೊಮೆಟೊ", "টমেটো", "ટમેટા", "തക്കാളി", "ਟਮਾਟਰ", "ଟମାଟୋ"],
        "onion": ["onion", "प्याज", "ఉల్లిపాయ", "வெங்காயம்", "kanda", "pyaj", "कांदा", "ಈರುಳ್ಳಿ", "পেঁয়াজ", "ડુંગળી", "സവാള", "ਪਿਆਜ਼", "ପିଆଜ"],
        "potato": ["potato", "आलू", "బంగాళాదుంప", "உருளைக்கிழங்கு", "aloo", "बटाटा", "ಆಲೂಗಡ್ಡೆ", "আলু", "બટાકા", "ഉരുളക്കിഴങ്ങ്", "ਆਲੂ", "ଆଳୁ"],
        "groundnut": ["groundnut", "peanut", "मूंगफली", "వేరుశెనగ", "கடலை", "நிலக்கடலை", "भुईमूग", "ಕಡಲೆಕಾಯಿ", "চীনাবাদাম", "મગફળી", "നിലക്കടല", "ਮੂੰਗਫਲੀ", "ଚିନାବାଦାମ"],
        "turmeric": ["turmeric", "हल्दी", "పసుపు", "மஞ்சள்", "haldi", "हळद", "ಅರಿಶಿನ", "হলুদ", "હળદર", "മഞ്ഞൾ", "ਹਲਦੀ", "ହଳଦୀ"],
        "arhar": ["arhar", "toor", "tur", "pigeon pea", "अरहर", "तूर", "కందులు", "துவரை", "ತೊಗರಿ", "অড়হর", "તુવેર", "തുവര", "ਅਰਹਰ", "ହରଡ଼"],
        "moong": ["moong", "mung", "green gram", "मूंग", "పెసలు", "பாசிப்பயறு", "मूग", "ಹೆಸರುಕಾಳು", "মুগ", "મગ", "ചെറുപയർ", "ਮੂੰਗੀ", "ମୁଗ"],
        "urad": ["urad", "black gram", "उड़द", "మినుములు", "உளுந்து", "उडीद", "ಉದ್ದಿನಕಾಳು", "মাষকলাই", "અડદ", "ഉഴുന്ന്", "ਮਾਂਹ", "ବିରି"],
        "masoor": ["masoor", "lentil", "red lentil", "मसूर", "మసూర్", "மசூர்", "मसूर डाळ", "ಮಸೂರ್", "মসুর", "મસૂર"],
        "bajra": ["bajra", "pearl millet", "बाजरा", "సజ్జ", "கம்பு", "बाजरी", "ಸಜ್ಜೆ", "বাজরা", "બાજરી", "കമ്പ്", "ਬਾਜਰਾ", "ବାଜରା"],
        "jowar": ["jowar", "sorghum", "ज्वार", "జొన్న", "சோளம்", "ज्वारी", "ಜೋಳ", "জোয়ার", "જુવાર", "ਜਵਾਰ", "ଜୁଆର"],
        "sunflower": ["sunflower", "सूरजमुखी", "పొద్దుతిరుగుడు", "சூரியகாந்தி", "सूर्यफूल", "ಸೂರ್ಯಕಾಂತಿ", "সূর্যমুখী", "સૂર્યમુખી", "സൂര്യകാന്തി", "ਸੂਰਜਮੁਖੀ", "ସୂର୍ଯ୍ୟମୁଖୀ"],
        "banana": ["banana", "केला", "అరటి", "வாழை", "kela", "केळे", "ಬಾಳೆಹಣ್ಣು", "কলা", "કેળાં", "വാഴപ്പഴം", "ਕੇਲਾ", "କଦଳୀ"],
        "mango": ["mango", "आम", "మామిడి", "மாம்பழம்", "aam", "आंबा", "ಮಾವಿನಹಣ್ಣು", "আম", "કેરી", "മാമ്പഴം", "ਅੰਬ", "ଆମ୍ବ"],
        "garlic": ["garlic", "लहसुन", "వెల్లుల్లి", "பூண்டு", "lahsun", "लसूण", "ಬೆಳ್ಳುಳ್ಳಿ", "রসুন", "લસણ", "വെളുത്തുള്ളി", "ਲਸਣ", "ରସୁଣ"],
        "ginger": ["ginger", "अदरक", "అల్లం", "இஞ்சி", "adrak", "आले", "ಶುಂಠಿ", "আদা", "આદું", "ഇഞ്ചി", "ਅਦਰਕ", "ଅଦା"],
    }

    STATES = {
        "Punjab": ["punjab", "पंजाब", "పంజాబ్", "பஞ்சாப்", "ਪੰਜਾਬ"],
        "Haryana": ["haryana", "हरियाणा", "హర్యానా", "ஹரியானா", "ਹਰਿਆਣਾ"],
        "Madhya Pradesh": ["madhya pradesh", "mp", "मध्य प्रदेश", "మధ్యప్రదేశ్", "மத்தியப் பிரதேசம்", "ਮੱਧ ਪ੍ਰਦੇਸ਼"],
        "Uttar Pradesh": ["uttar pradesh", "up", "उत्तर प्रदेश", "ఉత్తర ప్రదేశ్", "உத்தரப் பிரதேசம்", "ਉੱਤਰ ਪ੍ਰਦੇਸ਼"],
        "Tamil Nadu": ["tamil nadu", "tn", "तमिलनाडु", "தமிழ்நாடு", "తమిళనాడు", "ತಮಿಳುನಾಡು"],
        "Telangana": ["telangana", "तेलंगाना", "తెలంగాణ", "தெலுங்கானா"],
        "Andhra Pradesh": ["andhra pradesh", "ap", "आंध्र प्रदेश", "ఆంధ్రప్రదేశ్", "ஆந்திரப் பிரதேசம்"],
        "Maharashtra": ["maharashtra", "महाराष्ट्र", "మహారాష్ట్ర", "மகாராஷ்டிரா"],
        "Karnataka": ["karnataka", "कर्नाटक", "కర్ణాಟక", "கர்நாடகா"],
        "Gujarat": ["gujarat", "गुजरात", "గుజరాత్", "குஜராத்"],
        "Rajasthan": ["rajasthan", "राजस्थान", "రాజస్థాన్", "ராஜஸ்தான்"],
        "West Bengal": ["west bengal", "wb", "पश्चिम बंगाल", "পশ্চিমবঙ্গ"],
        "Bihar": ["bihar", "बिहार", "பீகார்"],
        "Odisha": ["odisha", "orissa", "ओडिशा", "ଓଡ଼ିଶା"],
        "Ladakh": ["ladakh", "लद्दाख"],
    }

    DISTRICTS = {
        "Indore": ["indore", "इंदौर", "இந்தூர்", "இந்தூரில்", "ఇండోర్", "ఇండోర్‌లో", "इंदूर", "ಇಂದೋರ್", "ইন্দোর", "ઇન્દોર", "ഇൻഡോർ", "ਇੰਦੌਰ", "ଇନ୍ଦୋର"],
        "Bhopal": ["bhopal", "भोपाल", "போபால்", "భోపాల్"],
        "Ujjain": ["ujjain", "उज्जैन", "உஜ்ஜைன்", "ఉజ్జయిని"],
        "Ludhiana": ["ludhiana", "लुधियाना", "ਲੁਧਿਆਣਾ", "లుధియానా", "லுதியானா"],
        "Karnal": ["karnal", "करनाल", "ਕਰਨਾਲ"],
        "Amritsar": ["amritsar", "अमृतसर", "ਅੰਮ੍ਰਿਤਸਰ"],
        "Guntur": ["guntur", "గుంటూరు", "गुंटूर", "குண்டூர்"],
        "Warangal": ["warangal", "వరంగల్", "वारंगल", "வாரங்கல்"],
        "Coimbatore": ["coimbatore", "கோயம்புத்தூர்", "கோவை", "கோவையில்", "కోయంబత్తూరు", "कोयंबटूर"],
        "Madurai": ["madurai", "மதுரை", "மதுரையில்", "మదురై", "मदुरै"],
        "Nashik": ["nashik", "नासिक", "नाशिक"],
        "Nagpur": ["nagpur", "नागपुर", "नागपूर"],
        "Barabanki": ["barabanki", "बाराबंकी"],
        "Tiruppur": ["tiruppur", "tirupur", "திருப்பூர்", "திருப்பூரில்", "తిరుప్పూర్", "తిరుప్పూర్‌లో", "तिरुप्पुर", "ತಿರುಪ್ಪುರ್", "তিরুপ্পুর", "તિરુપુર", "തിരുപ്പൂർ", "ਤਿਰੂਪੁਰ", "ତିରୁପୁର"],
        "Salem": ["salem", "சேலம்", "సేలం"],
        "Erode": ["erode", "ஈரோடு", "ఈరోడ్"],
        "Kurnool": ["kurnool", "కర్నూలు", "कुर्नूल"],
        "Vijayawada": ["vijayawada", "విజయవాడ", "विजयवाड़ा"],
        "Mysuru": ["mysuru", "mysore", "ಮೈಸೂರು", "मैसूर"],
        "Hubli": ["hubli", "hubballi", "ಹುಬ್ಬಳ್ಳಿ", "हुबली"],
        "Pune": ["pune", "पुणे", "பூனே", "పూణే"],
        "Solapur": ["solapur", "सोलापूर", "शोलापुर"],
        "Varanasi": ["varanasi", "banaras", "वाराणसी", "बनारस"],
        "Agra": ["agra", "आगरा"],
        "Patna": ["patna", "पटना"],
        "Bhubaneswar": ["bhubaneswar", "bhubaneshwar", "ଭୁବନେଶ୍ୱର", "भुवनेश्वर"],
    }

    # Canonical mapping of districts to their respective Indian states.
    # Enables automatic state derivation when a query explicitly identifies a known district.
    DISTRICT_TO_STATE: Dict[str, str] = {
        "Indore": "Madhya Pradesh",
        "Bhopal": "Madhya Pradesh",
        "Ujjain": "Madhya Pradesh",
        "Ludhiana": "Punjab",
        "Amritsar": "Punjab",
        "Karnal": "Haryana",
        "Guntur": "Andhra Pradesh",
        "Kurnool": "Andhra Pradesh",
        "Vijayawada": "Andhra Pradesh",
        "Warangal": "Telangana",
        "Coimbatore": "Tamil Nadu",
        "Madurai": "Tamil Nadu",
        "Tiruppur": "Tamil Nadu",
        "Salem": "Tamil Nadu",
        "Erode": "Tamil Nadu",
        "Nashik": "Maharashtra",
        "Nagpur": "Maharashtra",
        "Pune": "Maharashtra",
        "Solapur": "Maharashtra",
        "Barabanki": "Uttar Pradesh",
        "Varanasi": "Uttar Pradesh",
        "Agra": "Uttar Pradesh",
        "Mysuru": "Karnataka",
        "Hubli": "Karnataka",
        "Patna": "Bihar",
        "Bhubaneswar": "Odisha",
    }

    SEASONS = {
        "Kharif": ["kharif", "खरीफ", "ఖరీఫ్", "காரிஃப்"],
        "Rabi": ["rabi", "रबी", "రబీ", "ரபி"],
        "Zaid": ["zaid", "जायद"],
    }

    PESTS_DISEASES = {
        "Yellow stem borer": ["yellow stem borer", "stem borer", "तना छेदक", "కాండం తొలిచే పురుగు"],
        "Bollworm": ["bollworm", "pink bollworm", "गुलाबी सुंडी", "గులాబీ రంగు కాయ తొలుచు పురుగు"],
        "Blast": ["blast", "leaf blast", "झुलसा रोग", "ब्लास्ट", "అగ్గి తెగులు"],
        "Blight": ["blight", "bacterial blight", "ब्लाइट"],
        "Rust": ["rust", "brown rust", "yellow rust", "गेरुआ", "रतुआ"],
        "Aphids": ["aphid", "aphids", "माहू", "चेपा"],
        "Whitefly": ["whitefly", "सफेद मक्खी"],
    }

    GROWTH_STAGES = {
        "Sowing": ["sowing", "बुवाई", "विత్తనం"],
        "Vegetative": ["vegetative", "वानस्पतिक"],
        "Tillering": ["tillering", "कल्ले"],
        "Flowering": ["flowering", "फूल", "பூக்கும்"],
        "Grain filling": ["grain filling", "दाने"],
        "Harvesting": ["harvesting", "harvest", "कटाई"],
    }

    @staticmethod
    def _matches_entity(alias: str, text: str) -> bool:
        if alias.isascii():
            return bool(re.search(rf"\b{re.escape(alias)}\b", text))
        return alias in text

    def extract(self, query: str, initial_context: Optional[FarmerContextDTO] = None) -> FarmerContextDTO:
        """
        Extracts agricultural entities mentioned in the query.
        Applies context-aware precedence rules:
        1. Explicit location in current query > inherited/initial location context.
        2. If current query explicitly identifies a district whose canonical mapping determines a state:
           use the canonical state associated with that district (overriding stale inherited state).
        3. If current query explicitly specifies both state and district:
           use the current query values.
        4. If current query does not specify location:
           inherited farmer context may be used.
        5. If the current query contains an internally inconsistent location combination:
           preserve explicit query values without guessing so safe abstention can occur.
        """
        q_lower = query.lower()
        extracted: Dict[str, Any] = {}

        # 1. Extract crop from query (longest matching alias takes precedence to resolve compound aliases
        # such as 'green gram' -> Moong vs 'gram' -> Gram)
        best_crop = None
        best_len = 0
        for canonical, aliases in self.CROPS.items():
            for alias in aliases:
                if self._matches_entity(alias, q_lower) and len(alias) > best_len:
                    best_crop = canonical.capitalize()
                    best_len = len(alias)
        if best_crop:
            extracted["crop"] = best_crop

        # 2. Extract state from query
        for canonical, aliases in self.STATES.items():
            if any(self._matches_entity(alias, q_lower) for alias in aliases):
                extracted["state"] = canonical
                break

        # 3. Extract district from query
        for canonical, aliases in self.DISTRICTS.items():
            if any(self._matches_entity(alias, q_lower) for alias in aliases):
                extracted["district"] = canonical
                break

        # 4. Extract season from query
        for canonical, aliases in self.SEASONS.items():
            if any(self._matches_entity(alias, q_lower) for alias in aliases):
                extracted["season"] = canonical
                break

        # 5. Extract pest/disease from query
        for canonical, aliases in self.PESTS_DISEASES.items():
            if any(self._matches_entity(alias, q_lower) for alias in aliases):
                extracted["pest_disease"] = canonical
                break

        # 6. Extract growth stage from query
        for canonical, aliases in self.GROWTH_STAGES.items():
            if any(self._matches_entity(alias, q_lower) for alias in aliases):
                extracted["growth_stage"] = canonical
                break

        # Canonical State Resolution:
        # If the query explicitly identified a district, check canonical state mapping
        if "district" in extracted:
            canonical_state = self.DISTRICT_TO_STATE.get(extracted["district"])
            if "state" not in extracted and canonical_state:
                # Rule 2: Derive canonical state from explicit district
                extracted["state"] = canonical_state

        init_dict = initial_context.model_dump(exclude_none=True) if initial_context else {}

        # Crop precedence: Query explicit crop > Initial context crop
        crop = extracted.get("crop") or init_dict.get("crop")

        # Location precedence:
        if "district" in extracted:
            district = extracted["district"]
            # State is either explicit query state or canonical state derived from district;
            # do not inherit an incompatible state from init_dict
            state = extracted.get("state")
        elif "state" in extracted:
            state = extracted["state"]
            # If query specified state, only inherit initial district if it belongs to this state
            init_dist = init_dict.get("district")
            if init_dist and self.DISTRICT_TO_STATE.get(init_dist) == state:
                district = init_dist
            else:
                district = None
        else:
            # Rule 4: Neither state nor district in query -> safely inherit from initial context
            state = init_dict.get("state")
            district = init_dict.get("district")

        season = extracted.get("season") or init_dict.get("season")
        pest_disease = extracted.get("pest_disease") or init_dict.get("pest_disease")
        growth_stage = extracted.get("growth_stage") or init_dict.get("growth_stage")
        variety = extracted.get("variety") or init_dict.get("variety")
        market = extracted.get("market") or init_dict.get("market")
        language = extracted.get("language") or init_dict.get("language")

        return FarmerContextDTO(
            crop=crop,
            variety=variety,
            state=state,
            district=district,
            market=market,
            season=season,
            growth_stage=growth_stage,
            pest_disease=pest_disease,
            language=language,
        )


context_extractor = ContextExtractor()
