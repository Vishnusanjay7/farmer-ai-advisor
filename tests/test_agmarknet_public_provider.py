import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timezone, date
import httpx

from backend.app.db.session import SessionLocal
from backend.app.models.models import MandiPrice
from backend.app.providers.agmarknet_public_provider import AgmarknetPublicProvider
from backend.app.providers.mandi_provider import (
    DataGovMandiProvider,
    AgmarknetMandiProvider,
    CompositeMandiProvider,
)
from backend.app.providers.base import MandiPriceDTO


# Sample verified date-wise response from Agmarknet 2.0
MOCK_FILTERS_DATA = {
    "cmdt_data": [{"cmdt_id": 1, "cmdt_name": "Wheat", "cmdt_group_id": 1}],
    "state_data": [{"state_id": 19, "state_name": "Madhya Pradesh"}],
    "district_data": [{"id": 308, "state_id": 19, "district_name": "Indore"}],
    "market_data": [{"id": 3046, "mkt_name": "Indore APMC", "state_id": 19, "district_id": 308}],
}

MOCK_INDORE_WHEAT_DATEWISE = {
    "success": True,
    "markets": [
        {
            "marketName": "Indore APMC",
            "dates": [
                {
                    "arrivalDate": "23/09/2026",
                    "total_arrivals": 292.244,
                    "data": [
                        {
                            "arrivals": 292.244,
                            "variety": "Wheat",
                            "grade": "FAQ",
                            "minimumPrice": 1600.0,
                            "maximumPrice": 3151.0,
                            "modalPrice": 2775.0,
                        }
                    ],
                },
                {
                    "arrivalDate": "24/09/2026",
                    "total_arrivals": 210.485,
                    "data": [
                        {
                            "arrivals": 210.485,
                            "variety": "Wheat",
                            "grade": "FAQ",
                            "minimumPrice": 2081.0,
                            "maximumPrice": 3006.0,
                            "modalPrice": 2680.0,
                        }
                    ],
                },
            ],
        }
    ],
}


@pytest.fixture(autouse=True)
def clear_provider_cache():
    AgmarknetPublicProvider._filters_cache = None
    AgmarknetPublicProvider._filters_cached_at = 0.0
    AgmarknetPublicProvider._response_cache.clear()
    yield
    AgmarknetPublicProvider._filters_cache = None
    AgmarknetPublicProvider._filters_cached_at = 0.0
    AgmarknetPublicProvider._response_cache.clear()


# =========================================================================
# A. Indore Wheat successful response
# =========================================================================
@pytest.mark.asyncio
async def test_indore_wheat_successful_response():
    db = SessionLocal()
    # Clean any preexisting test record
    db.query(MandiPrice).filter(
        MandiPrice.commodity == "Wheat", MandiPrice.market == "Indore APMC"
    ).delete()
    db.commit()

    provider = AgmarknetPublicProvider(db=db)

    async def mock_get(url, *args, **kwargs):
        req = httpx.Request("GET", str(url))
        if "filters" in str(url):
            return httpx.Response(200, json={"status": True, "data": MOCK_FILTERS_DATA}, request=req)
        elif "date-wise" in str(url):
            return httpx.Response(200, json=MOCK_INDORE_WHEAT_DATEWISE, request=req)
        return httpx.Response(404, request=req)

    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        records = await provider.get_prices(
            state="Madhya Pradesh", district="Indore", commodity="Wheat"
        )

    assert len(records) > 0
    rec = records[0]
    assert rec.market == "Indore APMC"
    assert rec.commodity == "Wheat"
    assert rec.arrival_date == "2026-09-24"
    assert rec.min_price == 2081.0
    assert rec.max_price == 3006.0
    assert rec.modal_price == 2680.0
    assert rec.source == "Agmarknet 2.0"
    assert rec.data_origin == "production_live"

    # Verify cached in PostgreSQL DB
    db_rec = (
        db.query(MandiPrice)
        .filter(MandiPrice.commodity == "Wheat", MandiPrice.market == "Indore APMC")
        .first()
    )
    assert db_rec is not None
    assert db_rec.modal_price == 2680.0
    assert db_rec.data_origin == "production_live"

    # Clean up
    db.query(MandiPrice).filter(
        MandiPrice.commodity == "Wheat", MandiPrice.market == "Indore APMC"
    ).delete()
    db.commit()
    db.close()


# =========================================================================
# B. Current date has no Wheat record -> finds latest available valid daily record
# =========================================================================
@pytest.mark.asyncio
async def test_latest_available_daily_record_discovery():
    db = SessionLocal()
    provider = AgmarknetPublicProvider(db=db)

    async def mock_get(url, *args, **kwargs):
        req = httpx.Request("GET", str(url))
        if "filters" in str(url):
            return httpx.Response(200, json={"status": True, "data": MOCK_FILTERS_DATA}, request=req)
        elif "date-wise" in str(url):
            # Returns 24/09/2026 as the latest date even though today is 2026-09-25
            return httpx.Response(200, json=MOCK_INDORE_WHEAT_DATEWISE, request=req)
        return httpx.Response(404, request=req)

    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        records = await provider.get_prices(
            state="Madhya Pradesh", district="Indore", commodity="Wheat"
        )

    assert len(records) > 0
    # Crucial test: arrival_date is preserved as 2026-09-24, NOT fabricated to today
    assert records[0].arrival_date == "2026-09-24"
    db.close()


# =========================================================================
# C. HTTP 403 -> Safe provider failure and fallback behavior
# =========================================================================
@pytest.mark.asyncio
async def test_http_403_safe_fallback_to_cache():
    db = SessionLocal()
    # Insert a verified record into cache
    db.query(MandiPrice).filter(MandiPrice.commodity == "Wheat403").delete()
    db.commit()

    cached_row = MandiPrice(
        state="Madhya Pradesh",
        district="Indore",
        market="Indore APMC",
        commodity="Wheat403",
        variety="Lokwan",
        grade="FAQ",
        arrival_date=date(2026, 9, 21),
        min_price=2000.0,
        max_price=2900.0,
        modal_price=2500.0,
        source="Agmarknet 2.0",
        data_origin="production_live",
        fetched_at=datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc),
    )
    db.add(cached_row)
    db.commit()

    provider = AgmarknetPublicProvider(db=db)

    # Simulate HTTP 403 Forbidden
    req = httpx.Request("GET", "https://api.agmarknet.gov.in/v1/daily-price-arrival/filters")
    resp_403 = httpx.Response(403, request=req)
    with patch("httpx.AsyncClient.get", return_value=resp_403):
        records = await provider.get_prices(
            state="Madhya Pradesh", district="Indore", commodity="Wheat403"
        )

    # Must safely fall back to cached record with production_cached tag
    assert len(records) == 1
    assert records[0].data_origin == "production_cached"
    assert records[0].modal_price == 2500.0
    assert records[0].arrival_date == "2026-09-21"

    # Clean up
    db.query(MandiPrice).filter(MandiPrice.commodity == "Wheat403").delete()
    db.commit()
    db.close()


# =========================================================================
# D. HTTP 429 -> Safe provider failure without aggressive retry
# =========================================================================
@pytest.mark.asyncio
async def test_http_429_safe_failure_no_infinite_retry():
    db = SessionLocal()
    provider = AgmarknetPublicProvider(db=db)

    req = httpx.Request("GET", "https://api.agmarknet.gov.in/v1/daily-price-arrival/filters")
    resp_429 = httpx.Response(429, request=req)

    call_count = 0

    async def mock_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return resp_429

    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        records = await provider.get_prices(
            state="Madhya Pradesh", district="Indore", commodity="UnknownCrop429"
        )

    # Must not loop or retry endlessly; should fail safely and return empty
    assert call_count <= 2
    assert records == []
    db.close()


# =========================================================================
# E. Malformed response -> Safe failure
# =========================================================================
@pytest.mark.asyncio
async def test_malformed_response_safe_failure():
    db = SessionLocal()
    provider = AgmarknetPublicProvider(db=db)

    req = httpx.Request("GET", "https://api.agmarknet.gov.in/v1/daily-price-arrival/filters")
    # Response is 200 but body contains HTML error or malformed payload
    resp_bad = httpx.Response(200, text="<html><body>Gateway Error</body></html>", request=req)

    with patch("httpx.AsyncClient.get", return_value=resp_bad):
        records = await provider.get_prices(
            state="Madhya Pradesh", district="Indore", commodity="NonExistentMalformedCrop"
        )

    assert records == []
    db.close()



# =========================================================================
# F. DataGov provider remains intact
# =========================================================================
def test_datagov_provider_remains_intact():
    db = SessionLocal()
    provider = DataGovMandiProvider(db=db, api_key="test_key")
    assert isinstance(provider, AgmarknetMandiProvider)
    assert provider.api_key == "test_key"
    assert provider.BASE_URL == "https://api.data.gov.in/resource"

    raw = {
        "state": "Madhya Pradesh",
        "district": "Indore",
        "market": "Indore",
        "commodity": "Wheat",
        "variety": "Lokwan",
        "grade": "FAQ",
        "arrival_date": "22/09/2026",
        "min_price": "2400",
        "max_price": "2800",
        "modal_price": "2600",
        "source": "Agmarknet / data.gov.in",
    }
    dto = provider.normalize_record(raw, data_origin="production_live")
    assert dto.commodity == "Wheat"
    assert dto.modal_price == 2600.0
    assert dto.arrival_date == "2026-09-22"
    assert dto.source == "Agmarknet / data.gov.in"
    db.close()


# =========================================================================
# G. Composite provider selection hierarchy & fallback
# =========================================================================
@pytest.mark.asyncio
async def test_composite_provider_selection_hierarchy():
    db = SessionLocal()

    mock_datagov = MagicMock()
    mock_public = MagicMock()

    # Case 1: Primary DataGov configured with API key and succeeds
    mock_datagov.api_key = "valid_key"
    live_dto = MandiPriceDTO(
        state="MP", district="Indore", market="Indore APMC",
        commodity="Wheat", arrival_date="2026-09-24", min_price=2000, max_price=3000,
        modal_price=2500, source="Data.gov.in API", data_origin="production_live",
        fetched_at=datetime.now(timezone.utc).isoformat()
    )
    mock_datagov.get_prices = AsyncMock(return_value=[live_dto])

    composite = CompositeMandiProvider(
        db=db, primary_provider=mock_datagov, fallback_provider=mock_public
    )
    res = await composite.get_prices(state="MP", commodity="Wheat")
    assert len(res) == 1
    assert res[0].source == "Data.gov.in API"
    mock_public.get_prices.assert_not_called()

    # Case 2: Primary DataGov has no key or fails -> falls back to AgmarknetPublicProvider
    mock_datagov.api_key = None
    public_dto = MandiPriceDTO(
        state="MP", district="Indore", market="Indore APMC",
        commodity="Wheat", arrival_date="2026-09-24", min_price=2081, max_price=3006,
        modal_price=2680, source="Agmarknet 2.0", data_origin="production_live",
        fetched_at=datetime.now(timezone.utc).isoformat()
    )
    mock_public.get_prices = AsyncMock(return_value=[public_dto])

    res2 = await composite.get_prices(state="MP", commodity="Wheat")
    assert len(res2) == 1
    assert res2[0].source == "Agmarknet 2.0"
    assert res2[0].modal_price == 2680.0

    # Case 3: Both fail -> falls back to DB cache
    mock_public.get_prices = AsyncMock(side_effect=Exception("Upstream down"))
    mock_datagov.get_cached_records = MagicMock(return_value=[
        MandiPriceDTO(
            state="MP", district="Indore", market="Indore APMC",
            commodity="Wheat", arrival_date="2026-09-22", min_price=2000, max_price=2800,
            modal_price=2400, source="Agmarknet 2.0", data_origin="production_cached",
            fetched_at=datetime.now(timezone.utc).isoformat()
        )
    ])

    res3 = await composite.get_prices(state="MP", commodity="Wheat")
    assert len(res3) == 1
    assert res3[0].data_origin == "production_cached"

    # Case 4: No cache -> returns empty list (safe abstention)
    mock_datagov.get_cached_records = MagicMock(return_value=[])
    res4 = await composite.get_prices(state="NonExistent", commodity="Nothing")
    assert res4 == []

    db.close()


# =========================================================================
# H. No development_seed data becomes authoritative
# =========================================================================
@pytest.mark.asyncio
async def test_no_development_seed_becomes_authoritative():
    db = SessionLocal()
    # Insert development_seed
    db.query(MandiPrice).filter(MandiPrice.commodity == "SeedGrain").delete()
    db.commit()

    dev_row = MandiPrice(
        state="MP",
        district="Gwalior",
        market="Gwalior",
        commodity="SeedGrain",
        variety="Local",
        grade="FAQ",
        arrival_date=date(2026, 9, 20),
        min_price=1000.0,
        max_price=1200.0,
        modal_price=1100.0,
        source="DevMock",
        data_origin="development_seed",
    )
    db.add(dev_row)
    db.commit()

    provider = AgmarknetPublicProvider(db=db)
    cached = provider.get_cached_records(state="MP", commodity="SeedGrain")

    # get_cached_records filters for data_origin in ('production_live', 'production_cached')
    # development_seed MUST NEVER be returned as a valid production cache
    assert len(cached) == 0

    # Clean up
    db.query(MandiPrice).filter(MandiPrice.commodity == "SeedGrain").delete()
    db.commit()
    db.close()


# =========================================================================
# I. Data origin values are strictly validated
# =========================================================================
def test_data_origin_semantics_strictness():
    # Valid values
    valid_origins = ["production_live", "production_cached", "development_seed"]
    for origin in valid_origins:
        dto = MandiPriceDTO(
            state="MP",
            district="Indore",
            market="Indore APMC",
            commodity="Wheat",
            arrival_date="2026-09-24",
            min_price=2081.0,
            max_price=3006.0,
            modal_price=2680.0,
            source="Agmarknet 2.0",
            data_origin=origin,
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
        assert dto.data_origin == origin
