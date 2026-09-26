import pytest
import httpx
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.schemas.advisor import (
    AgriculturalIntent,
    AdvisorQueryRequest,
    FarmerContextDTO,
)
from backend.app.schemas.weather import (
    WeatherData,
    WeatherCurrentDTO,
    WeatherForecastDayDTO,
    WeatherSoilDTO,
    WeatherSignalsDTO,
    LocationMetadataDTO,
    LocationResolutionMethod,
)
from backend.app.services.location_resolver import location_resolver, LocationResolver
from backend.app.providers.weather_provider import (
    OpenMeteoProvider,
    open_meteo_provider,
    get_wmo_description,
)
from backend.app.services.intent_classifier import intent_classifier
from backend.app.services.weather_rules import (
    AGRONOMIC_RULE_AUDIT_REGISTRY,
    summarize_weather_facts,
)
from backend.app.services.grounding_validator import grounding_validator
from backend.app.services.advisor_orchestrator import advisor_orchestrator


MOCK_OPEN_METEO_PAYLOAD = {
    "latitude": 22.72,
    "longitude": 75.86,
    "generationtime_ms": 0.12,
    "utc_offset_seconds": 19800,
    "timezone": "Asia/Kolkata",
    "timezone_abbreviation": "IST",
    "elevation": 553.0,
    "current": {
        "time": "2026-09-26T15:00",
        "interval": 900,
        "temperature_2m": 29.5,
        "relative_humidity_2m": 65,
        "precipitation": 0.2,
        "weather_code": 51,
        "wind_speed_10m": 16.5,
        "wind_direction_10m": 240,
    },
    "daily": {
        "time": ["2026-09-26", "2026-09-27", "2026-09-28"],
        "weather_code": [51, 61, 0],
        "temperature_2m_max": [31.0, 32.5, 33.0],
        "temperature_2m_min": [22.0, 23.0, 21.5],
        "precipitation_sum": [1.5, 5.0, 0.0],
        "precipitation_probability_max": [45, 75, 10],
        "wind_speed_10m_max": [18.0, 22.5, 12.0],
        "et0_fao_evapotranspiration": [4.6, 4.2, 5.1],
    },
    "hourly": {
        "soil_temperature_0_to_10cm": [26.2, 26.0, 25.8],
        "soil_moisture_0_to_1cm": [0.285, 0.284, 0.283],
    },
}


from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import uuid
from backend.app.db.session import Base, get_db
from backend.app.models.models import SourceDocument, KnowledgeChunk
from backend.app.providers.embedding_provider import DeterministicMockEmbeddingProvider


@pytest.fixture
def weather_test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    doc = SourceDocument(
        id=str(uuid.uuid4()),
        title="CICR Cotton Pest Guidelines",
        source_name="CICR",
        source_type="ICAR",
        issuing_authority="ICAR - Central Institute for Cotton Research",
        state_applicability="All-India",
        official_document_url="https://cicr.org.in/cotton_ipm.pdf",
        publication_year=2024,
    )
    db.add(doc)
    db.flush()

    emb = DeterministicMockEmbeddingProvider().generate_embedding_sync("pink bollworm in cotton")
    chunk = KnowledgeChunk(
        id=str(uuid.uuid4()),
        document_id=doc.id,
        chunk_index=0,
        crop_name="Cotton",
        content="Pink bollworm in cotton management: Chlorpyrifos 20% EC @ 500 ml/acre strictly when ETL of 8 moths per trap is crossed.",
        content_hash="mock-hash-cotton-123",
        token_count=35,
        embedding=emb,
        chunk_metadata={"crop": "cotton", "pest_disease": "pink bollworm"},
    )
    db.add(chunk)
    db.commit()

    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(weather_test_db):
    def override_get_db():
        try:
            yield weather_test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


# ==============================================================================
# TEST 1: Open-Meteo Response Parsing
# ==============================================================================

def test_open_meteo_response_parsing():
    """Verifies complete parsing of Open-Meteo JSON into structured Pydantic DTOs."""
    provider = OpenMeteoProvider()
    loc = LocationMetadataDTO(
        latitude=22.7196,
        longitude=75.8577,
        resolved_name="Indore District Centroid",
        resolution_method=LocationResolutionMethod.DISTRICT_CENTROID,
        state="Madhya Pradesh",
        district="Indore",
    )

    data = provider._parse_response(MOCK_OPEN_METEO_PAYLOAD, loc)

    assert data.source == "Open-Meteo"
    assert data.source_type == "weather_model"
    assert data.data_origin == "production_live"
    assert data.location.resolved_name == "Indore District Centroid"
    assert data.current.temperature == 29.5
    assert data.current.relative_humidity == 65
    assert data.current.precipitation == 0.2
    assert data.current.weather_code == 51
    assert data.current.weather_description == "Light drizzle"
    assert data.current.wind_speed == 16.5

    assert len(data.forecast_days) == 3
    assert data.forecast_days[0].date == "2026-09-26"
    assert data.forecast_days[0].temp_max == 31.0
    assert data.forecast_days[0].temp_min == 22.0
    assert data.forecast_days[0].precipitation_sum == 1.5
    assert data.forecast_days[0].precipitation_probability_max == 45
    assert data.forecast_days[0].et0_evapotranspiration == 4.6

    assert data.soil is not None
    assert data.soil.soil_temperature_0_to_10cm == 26.2
    assert data.soil.soil_moisture_0_to_1cm == 0.285

    # Signals computation
    assert data.signals.rain_expected is True  # 45% and 75% in forecast
    assert data.signals.high_wind_signal is True  # Day 2 wind is 22.5 >= 20.0
    assert data.signals.dry_period_signal is False


# ==============================================================================
# TEST 2: Timeout Handling and No Fabricated Weather
# ==============================================================================

@pytest.mark.asyncio
async def test_timeout_handling_and_no_fabricated_weather():
    """Verifies provider returns None upon HTTP timeout and NEVER fabricates fake weather."""
    provider = OpenMeteoProvider(timeout_seconds=0.1)
    loc = LocationMetadataDTO(
        latitude=22.7196,
        longitude=75.8577,
        resolved_name="Indore District Centroid",
        resolution_method=LocationResolutionMethod.DISTRICT_CENTROID,
    )

    mock_client = AsyncMock()
    mock_client.get.side_effect = httpx.TimeoutException("Read timed out")

    result = await provider.fetch_weather(location=loc, client=mock_client)
    assert result is None, "Weather provider must return None on timeout without fabricating fake numbers."


# ==============================================================================
# TEST 3: In-Memory Cache Behavior
# ==============================================================================

@pytest.mark.asyncio
async def test_weather_cache_behavior():
    """Verifies that duplicate calls within TTL are served from cache with production_cached origin."""
    provider = OpenMeteoProvider(cache_ttl_seconds=60)
    loc = LocationMetadataDTO(
        latitude=22.7196,
        longitude=75.8577,
        resolved_name="Indore District Centroid",
        resolution_method=LocationResolutionMethod.DISTRICT_CENTROID,
    )

    mock_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = MOCK_OPEN_METEO_PAYLOAD
    mock_resp.raise_for_status = MagicMock()
    mock_client.get.return_value = mock_resp

    # First fetch: live
    res1 = await provider.fetch_weather(location=loc, client=mock_client)
    assert res1 is not None
    assert res1.data_origin == "production_live"
    assert res1.cached is False
    assert mock_client.get.call_count == 1

    # Second fetch: cached
    res2 = await provider.fetch_weather(location=loc, client=mock_client)
    assert res2 is not None
    assert res2.data_origin == "production_cached"
    assert res2.cached is True
    assert mock_client.get.call_count == 1, "Cache hit must not execute a network request."

    # Force refresh bypasses cache
    res3 = await provider.fetch_weather(location=loc, client=mock_client, force_refresh=True)
    assert res3 is not None
    assert res3.data_origin == "production_live"
    assert mock_client.get.call_count == 2


# ==============================================================================
# TEST 4: Location Resolution Precedence and Safety Labelling
# ==============================================================================

def test_location_precedence_and_safety():
    """
    Verifies location hierarchy:
    1. GPS -> gps_coordinates
    2. District -> district_centroid (NEVER called 'field location')
    3. State -> state_centroid
    4. Fallback -> default_fallback
    """
    resolver = LocationResolver()

    # 1. GPS coordinates take absolute precedence
    gps_loc = resolver.resolve(latitude=18.5204, longitude=73.8567, district="Indore", state="Madhya Pradesh")
    assert gps_loc is not None
    assert gps_loc.resolution_method == LocationResolutionMethod.GPS_COORDINATES
    assert gps_loc.latitude == 18.5204
    assert gps_loc.longitude == 73.8567

    # 2. District centroid
    dist_loc = resolver.resolve(district="Indore")
    assert dist_loc is not None
    assert dist_loc.resolution_method == LocationResolutionMethod.DISTRICT_CENTROID
    assert dist_loc.resolved_name == "Indore District Centroid"
    assert "field location" not in dist_loc.resolved_name.lower()
    assert dist_loc.state == "Madhya Pradesh"
    assert dist_loc.latitude == 22.7196
    assert dist_loc.longitude == 75.8577

    # 3. State centroid
    state_loc = resolver.resolve(state="Punjab")
    assert state_loc is not None
    assert state_loc.resolution_method == LocationResolutionMethod.STATE_CENTROID
    assert state_loc.resolved_name == "Punjab State Centroid"

    # 4. Fallback
    fallback_loc = resolver.resolve(allow_default=True)
    assert fallback_loc is not None
    assert fallback_loc.resolution_method == LocationResolutionMethod.DEFAULT_FALLBACK

    # 5. Fallback disabled
    no_loc = resolver.resolve(allow_default=False)
    assert no_loc is None


# ==============================================================================
# TEST 5: Weather Intents & Multilingual Classification
# ==============================================================================

def test_multilingual_weather_intent_classification():
    """Verifies that weather queries classify into dedicated WEATHER_* intents across 11 languages."""
    cases = [
        # English
        ("Will it rain tomorrow in Indore?", AgriculturalIntent.WEATHER_RAIN),
        ("What is today's temperature in Ludhiana?", AgriculturalIntent.WEATHER_TEMPERATURE),
        ("Weather forecast for next 3 days", AgriculturalIntent.WEATHER_FORECAST),
        ("What is the current weather right now?", AgriculturalIntent.WEATHER_CURRENT),
        ("How is the weather near Pune?", AgriculturalIntent.WEATHER_ADVISORY),

        # Hindi
        ("क्या कल इंदौर में बारिश होगी?", AgriculturalIntent.WEATHER_RAIN),
        ("आज का तापमान कितना है?", AgriculturalIntent.WEATHER_TEMPERATURE),
        ("कल का मौसम कैसा रहेगा?", AgriculturalIntent.WEATHER_FORECAST),
        ("अभी मौसम कैसा है?", AgriculturalIntent.WEATHER_CURRENT),
        ("मौसम कैसा है?", AgriculturalIntent.WEATHER_CURRENT),

        # Telugu
        ("రేపు వర్షం పడుతుందా?", AgriculturalIntent.WEATHER_RAIN),
        ("ఈ రోజు ఉష్ణోగ్రత ఎంత?", AgriculturalIntent.WEATHER_TEMPERATURE),
        ("రేపటి వాతావరణం ఎలా ఉంటుంది?", AgriculturalIntent.WEATHER_FORECAST),
        ("ప్రస్తుత వాతావరణం ఎలా ఉంది?", AgriculturalIntent.WEATHER_CURRENT),

        # Tamil
        ("நாளை மழை பெய்யுமா?", AgriculturalIntent.WEATHER_RAIN),
        ("இன்றைய வெப்பநிலை என்ன?", AgriculturalIntent.WEATHER_TEMPERATURE),
        ("நாளை வானிலை எப்படி இருக்கும்?", AgriculturalIntent.WEATHER_FORECAST),
        ("தற்போதைய வானிலை என்ன?", AgriculturalIntent.WEATHER_CURRENT),

        # Marathi
        ("उद्या पाऊस पडेल का?", AgriculturalIntent.WEATHER_RAIN),
        ("आजचे तापमान किती आहे?", AgriculturalIntent.WEATHER_TEMPERATURE),
        ("हवामान अंदाज काय आहे?", AgriculturalIntent.WEATHER_FORECAST),
        ("आजचे हवामान कसे आहे?", AgriculturalIntent.WEATHER_CURRENT),

        # Kannada
        ("ನಾಳೆ ಮಳೆ ಬರುತ್ತದೆಯೇ?", AgriculturalIntent.WEATHER_RAIN),
        ("ಇಂದಿನ ತಾಪಮಾನ ಎಷ್ಟು?", AgriculturalIntent.WEATHER_TEMPERATURE),

        # Bengali
        ("কাল কি বৃষ্টি হবে?", AgriculturalIntent.WEATHER_RAIN),

        # Gujarati
        ("કાલે વરસાદ પડશે?", AgriculturalIntent.WEATHER_RAIN),

        # Malayalam
        ("നാളെ മഴ പെയ്യുമോ?", AgriculturalIntent.WEATHER_RAIN),

        # Punjabi
        ("ਕੀ ਕੱਲ੍ਹ ਮੀਂਹ ਪਵੇਗਾ?", AgriculturalIntent.WEATHER_RAIN),

        # Odia
        ("ଆସନ୍ତାକାଲି ବର୍ଷା ହେବ କି?", AgriculturalIntent.WEATHER_RAIN),
    ]

    for q, expected in cases:
        detected, conf = intent_classifier.classify(q)
        assert detected == expected, f"Query '{q}' classified as {detected}, expected {expected}"


# ==============================================================================
# TEST 6: Weather REST API Endpoint (GET /api/v1/weather)
# ==============================================================================

def test_weather_api_endpoint(client):
    """Verifies GET /api/v1/weather endpoint behavior."""
    with patch("backend.app.providers.weather_provider.open_meteo_provider.fetch_weather") as mock_fetch:
        loc = LocationMetadataDTO(
            latitude=22.7196,
            longitude=75.8577,
            resolved_name="Indore District Centroid",
            resolution_method=LocationResolutionMethod.DISTRICT_CENTROID,
            state="Madhya Pradesh",
            district="Indore",
        )
        mock_data = open_meteo_provider._parse_response(MOCK_OPEN_METEO_PAYLOAD, loc)
        mock_fetch.return_value = mock_data

        # 1. District Centroid query
        res = client.get("/api/v1/weather?district=Indore")
        assert res.status_code == 200
        json_data = res.json()
        assert json_data["status"] == "ok"
        assert json_data["weather"]["location"]["resolved_name"] == "Indore District Centroid"
        assert json_data["weather"]["location"]["resolution_method"] == "district_centroid"
        assert json_data["weather"]["current"]["temperature"] == 29.5
        assert "disclaimer" in json_data
        assert "Open-Meteo" in json_data["disclaimer"]

        # 2. GPS query
        gps_loc = LocationMetadataDTO(
            latitude=18.5204,
            longitude=73.8567,
            resolved_name="GPS Coordinates (18.5204, 73.8567)",
            resolution_method=LocationResolutionMethod.GPS_COORDINATES,
        )
        mock_fetch.return_value = open_meteo_provider._parse_response(MOCK_OPEN_METEO_PAYLOAD, gps_loc)

        res_gps = client.get("/api/v1/weather?latitude=18.5204&longitude=73.8567")
        assert res_gps.status_code == 200
        assert res_gps.json()["weather"]["location"]["resolution_method"] == "gps_coordinates"


# ==============================================================================
# TEST 7: Deterministic Weather-Only Advisor Response & Provenance Citations
# ==============================================================================

@pytest.mark.asyncio
async def test_weather_only_query_deterministic_response(weather_test_db):
    """Verifies pure weather queries are formatted deterministically without calling LLM."""
    with patch("backend.app.providers.weather_provider.open_meteo_provider.fetch_weather") as mock_fetch:
        loc = LocationMetadataDTO(
            latitude=22.7196,
            longitude=75.8577,
            resolved_name="Indore District Centroid",
            resolution_method=LocationResolutionMethod.DISTRICT_CENTROID,
            state="Madhya Pradesh",
            district="Indore",
        )
        mock_data = open_meteo_provider._parse_response(MOCK_OPEN_METEO_PAYLOAD, loc)
        mock_fetch.return_value = mock_data

        req = AdvisorQueryRequest(
            query="Will it rain tomorrow in Indore?",
            language="en-IN",
        )

        response = await advisor_orchestrator.answer_query(db=weather_test_db, request=req)

        assert response.is_grounded is True
        assert response.abstained is False
        assert response.llm_called is False, "Pure weather query must be formatted deterministically."
        assert "Indore District Centroid" in response.response_text
        assert "29.5" in response.response_text or "32.5" in response.response_text
        assert "Open-Meteo" in response.response_text

        # Citation verification
        weather_citations = [c for c in response.citations if c.source_type == "weather_model"]
        assert len(weather_citations) >= 1
        assert weather_citations[0].issuing_authority == "Open-Meteo Weather Model"
        assert weather_citations[0].location_resolution_method == "district_centroid"


# ==============================================================================
# TEST 8: Weather Failure Regional Abstention
# ==============================================================================

@pytest.mark.asyncio
async def test_weather_unavailable_regional_abstention(weather_test_db):
    """Verifies that when Open-Meteo fails for a weather query, the system abstains safely in regional language."""
    with patch("backend.app.providers.weather_provider.open_meteo_provider.fetch_weather") as mock_fetch:
        mock_fetch.return_value = None  # Open-Meteo failure

        # Hindi weather query
        req_hi = AdvisorQueryRequest(
            query="क्या कल बारिश होगी?",
            language="hi-IN",
        )
        res_hi = await advisor_orchestrator.answer_query(db=weather_test_db, request=req_hi)

        assert res_hi.abstained is True
        assert res_hi.is_grounded is False
        assert "ओपन-मेटियो मौसम सेवा वर्तमान में अनुपलब्ध है" in res_hi.response_text

        # Telugu weather query
        req_te = AdvisorQueryRequest(
            query="రేపు వర్షం పడుతుందా?",
            language="te-IN",
        )
        res_te = await advisor_orchestrator.answer_query(db=weather_test_db, request=req_te)
        assert res_te.abstained is True
        assert "ఓపెన్-మెటియో వాతావరణ సేవ ప్రస్తుతం అందుబాటులో లేదు" in res_te.response_text


# ==============================================================================
# TEST 9: Weather Unavailable + Agricultural Evidence Available
# ==============================================================================

@pytest.mark.asyncio
async def test_weather_unavailable_agricultural_evidence_available(weather_test_db):
    """
    Verifies that when Open-Meteo fails during an agricultural operation query
    (e.g., controlling a pest), the system DOES NOT crash or abstain, but successfully
    answers from the authoritative agricultural knowledge base.
    """
    with patch("backend.app.providers.weather_provider.open_meteo_provider.fetch_weather") as mock_fetch, \
         patch("backend.app.providers.llm_provider.LLMProvider.generate_grounded_response") as mock_llm:

        mock_fetch.return_value = None  # Weather service unavailable

        # Mock LLM response for pest management
        from backend.app.providers.base import LLMGroundedResponse
        mock_llm.return_value = LLMGroundedResponse(
            answer_text="According to ICAR-CICR Cotton Pest Guidelines, manage pink bollworm using pheromone traps and Chlorpyrifos 20% EC @ 500 ml/acre strictly when ETL of 8 moths per trap is crossed.",
            language_code="en-IN",
            intent="PEST_DISEASE",
            citations=[],
            is_grounded=True,
        )

        req = AdvisorQueryRequest(
            query="How to control pink bollworm in cotton?",
            language="en-IN",
        )

        from backend.app.services.retrieval_service import RetrievalService
        from backend.app.providers.embedding_provider import DeterministicMockEmbeddingProvider
        from backend.app.services.advisor_orchestrator import AdvisorOrchestrator

        retrieval = RetrievalService(embedding_provider=DeterministicMockEmbeddingProvider(dimension=768))
        custom_orchestrator = AdvisorOrchestrator(retrieval=retrieval)

        response = await custom_orchestrator.answer_query(db=weather_test_db, request=req)

        assert response.is_grounded is True
        assert response.abstained is False
        assert any("Cotton" in c.issuing_authority or "CICR" in c.title for c in response.citations)


# ==============================================================================
# TEST 10: Agronomic Rule Audit Registry Integrity
# ==============================================================================

def test_agronomic_rule_audit_registry_integrity():
    """
    Verifies Task 2 & Task 3 safety mandate:
    All 8 candidate agronomic rules (spraying/rain, spraying/wind, irrigation/rainfall,
    irrigation/ET0, irrigation/soil moisture, harvesting/rain, heat stress, frost stress)
    must be audited, marked EVIDENCE_UNAVAILABLE, and NOT implemented as universal prescriptions.
    """
    assert len(AGRONOMIC_RULE_AUDIT_REGISTRY) == 8

    operations = [entry.operation for entry in AGRONOMIC_RULE_AUDIT_REGISTRY]
    assert "spraying / rain" in operations
    assert "spraying / wind" in operations
    assert "irrigation / rainfall" in operations
    assert "irrigation / ET0" in operations
    assert "irrigation / soil moisture" in operations
    assert "harvesting / rain" in operations
    assert "heat stress" in operations
    assert "frost / cold stress" in operations

    for entry in AGRONOMIC_RULE_AUDIT_REGISTRY:
        assert entry.authoritative_status == "EVIDENCE_UNAVAILABLE", (
            f"Rule {entry.rule_id} must be marked EVIDENCE_UNAVAILABLE because it is not in the verified corpus."
        )
        assert entry.implemented is False, (
            f"Rule {entry.rule_id} must NOT be implemented as a universal deterministic rule."
        )


# ==============================================================================
# TEST 11: Neutral Weather Signal Summary
# ==============================================================================

def test_neutral_weather_signals():
    """Verifies summarize_weather_facts extracts neutral meteorological facts without agronomic prescriptions."""
    loc = LocationMetadataDTO(
        latitude=22.7196,
        longitude=75.8577,
        resolved_name="Indore District Centroid",
        resolution_method=LocationResolutionMethod.DISTRICT_CENTROID,
    )
    data = open_meteo_provider._parse_response(MOCK_OPEN_METEO_PAYLOAD, loc)
    summary = summarize_weather_facts(data)

    assert summary.location_name == "Indore District Centroid"
    assert summary.current_temp == 29.5
    assert summary.current_humidity == 65
    assert summary.rain_expected is True
    assert summary.precipitation_sum_3d == 6.5
    assert summary.max_rain_probability_3d == 75
    assert summary.et0_today == 4.6

    # Verify signals are neutral statements of fact
    for s in summary.signals_summary:
        assert "DO_NOT_SPRAY" not in s
        assert "VETO" not in s
        assert "BAN" not in s
        assert "IRRIGATE_IMMEDIATELY" not in s
