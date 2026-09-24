import re
from typing import Optional, Dict, Any
from backend.app.schemas.advisor import FarmerContextDTO


class ContextExtractor:
    """
    Extracts agricultural context strictly when explicitly mentioned in the query.
    Never hallucinates or guesses unmentioned entities.
    """

    CROPS = {
        "paddy": ["paddy", "rice", "धान", "चावल", "వరి", "நெல்", "भात"],
        "wheat": ["wheat", "गेहूं", "गेंहू", "గోధుమ", "கோதுமை", "गहू"],
        "cotton": ["cotton", "कपास", "पत्ती", "பருத்தி", "कापूस"],
        "chili": ["chili", "chilli", "mirchi", "मिर्च", "మిరప", "மிளகாய்", "मिरची"],
        "soybean": ["soybean", "soyabean", "सोयाबीन", "సోయాబీన్"],
        "maize": ["maize", "corn", "मक्का", "మొక్కజొన్న"],
        "sugarcane": ["sugarcane", "गन्ना", "చెరకు"],
        "mustard": ["mustard", "सरसों", "ఆవాలు"],
        "gram": ["gram", "chana", "चना", "శనగలు"],
        "dragon fruit": ["dragon fruit", "pitaya", "ड्रैगन फ्रूट", "कमलम"],
    }

    STATES = {
        "Punjab": ["punjab", "पंजाब", "పంజాబ్"],
        "Haryana": ["haryana", "हरियाणा", "హర్యానా"],
        "Madhya Pradesh": ["madhya pradesh", "mp", "मध्य प्रदेश", "మధ్యప్రదేశ్"],
        "Uttar Pradesh": ["uttar pradesh", "up", "उत्तर प्रदेश", "ఉత్తర ప్రదేశ్"],
        "Tamil Nadu": ["tamil nadu", "tn", "तमिलनाडु", "தமிழ்நாடு"],
        "Telangana": ["telangana", "तेलंगाना", "తెలంగాణ"],
        "Andhra Pradesh": ["andhra pradesh", "ap", "आंध्र प्रदेश", "ఆంధ్రప్రదేశ్"],
        "Maharashtra": ["maharashtra", "महाराष्ट्र", "మహారాష్ట్ర"],
        "Karnataka": ["karnataka", "कर्नाटक", "కర్ణాటక"],
        "Gujarat": ["gujarat", "गुजरात", "గుజరాత్"],
        "Rajasthan": ["rajasthan", "राजस्थान", "రాజస్థాన్"],
        "West Bengal": ["west bengal", "wb", "पश्चिम बंगाल"],
        "Bihar": ["bihar", "बिहार"],
        "Odisha": ["odisha", "orissa", "ओडिशा"],
        "Ladakh": ["ladakh", "लद्दाख"],
    }

    DISTRICTS = {
        "Indore": ["indore", "इंदौर"],
        "Bhopal": ["bhopal", "भोपाल"],
        "Ujjain": ["ujjain", "उज्जैन"],
        "Ludhiana": ["ludhiana", "लुधियाना"],
        "Karnal": ["karnal", "करनाल"],
        "Amritsar": ["amritsar", "अमृतसर"],
        "Guntur": ["guntur", "గుంటూరు"],
        "Warangal": ["warangal", "వరంగల్"],
        "Coimbatore": ["coimbatore", "கோயம்புத்தூர்"],
        "Madurai": ["madurai", "மதுரை"],
        "Nashik": ["nashik", "नासिक"],
        "Nagpur": ["nagpur", "नागपुर"],
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
        Falls back to initial_context if already present, but never invents values.
        """
        ctx = initial_context.model_dump() if initial_context else {}
        q_lower = query.lower()

        # Extract crop
        if not ctx.get("crop"):
            for canonical, aliases in self.CROPS.items():
                if any(self._matches_entity(alias, q_lower) for alias in aliases):
                    ctx["crop"] = canonical.capitalize()
                    break

        # Extract state
        if not ctx.get("state"):
            for canonical, aliases in self.STATES.items():
                if any(self._matches_entity(alias, q_lower) for alias in aliases):
                    ctx["state"] = canonical
                    break

        # Extract district
        if not ctx.get("district"):
            for canonical, aliases in self.DISTRICTS.items():
                if any(self._matches_entity(alias, q_lower) for alias in aliases):
                    ctx["district"] = canonical
                    break

        # Extract season
        if not ctx.get("season"):
            for canonical, aliases in self.SEASONS.items():
                if any(self._matches_entity(alias, q_lower) for alias in aliases):
                    ctx["season"] = canonical
                    break

        # Extract pest/disease
        if not ctx.get("pest_disease"):
            for canonical, aliases in self.PESTS_DISEASES.items():
                if any(self._matches_entity(alias, q_lower) for alias in aliases):
                    ctx["pest_disease"] = canonical
                    break

        # Extract growth stage
        if not ctx.get("growth_stage"):
            for canonical, aliases in self.GROWTH_STAGES.items():
                if any(self._matches_entity(alias, q_lower) for alias in aliases):
                    ctx["growth_stage"] = canonical
                    break

        return FarmerContextDTO(
            crop=ctx.get("crop"),
            variety=ctx.get("variety"),
            state=ctx.get("state"),
            district=ctx.get("district"),
            market=ctx.get("market"),
            season=ctx.get("season"),
            growth_stage=ctx.get("growth_stage"),
            pest_disease=ctx.get("pest_disease"),
            language=ctx.get("language"),
        )


context_extractor = ContextExtractor()
