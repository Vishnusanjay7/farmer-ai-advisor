import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, date
from backend.app.db.session import SessionLocal
from backend.app.providers.mandi_provider import AgmarknetMandiProvider
from backend.app.models.models import MandiPrice


def test_mandi_response_normalization_and_date_handling():
    db = SessionLocal()
    provider = AgmarknetMandiProvider(db=db, api_key="dummy_key")

    raw_record = {
        "state": "Madhya Pradesh",
        "district": "Indore",
        "market": "Indore",
        "commodity": "Wheat",
        "variety": "Lokwan",
        "grade": "FAQ",
        "arrival_date": "22/09/2026",  # DD/MM/YYYY format
        "min_price": "2450",
        "max_price": "2850",
        "modal_price": "2650",
        "source": "Agmarknet",
    }

    dto = provider.normalize_record(raw_record, data_origin="production_live")

    # Verify normalization
    assert dto.state == "Madhya Pradesh"
    assert dto.commodity == "Wheat"
    assert dto.arrival_date == "2026-09-22"  # ISO YYYY-MM-DD
    assert dto.min_price == 2450.0
    assert dto.max_price == 2850.0
    assert dto.modal_price == 2650.0
    assert dto.data_origin == "production_live"
    assert dto.fetched_at is not None
    db.close()


def test_mandi_caching_and_data_origin_separation():
    db = SessionLocal()
    provider = AgmarknetMandiProvider(db=db)

    # Clean existing test records
    db.query(MandiPrice).filter(MandiPrice.commodity == "TestBarley").delete()
    db.commit()

    raw_record = {
        "state": "Rajasthan",
        "district": "Jaipur",
        "market": "Jaipur",
        "commodity": "TestBarley",
        "arrival_date": "2026-09-20",
        "min_price": "1800",
        "max_price": "2100",
        "modal_price": "1950",
    }
    dto = provider.normalize_record(raw_record, data_origin="production_live")
    provider.cache_records([dto])

    # Query cached records
    cached = provider.get_cached_records(state="Rajasthan", commodity="TestBarley")
    assert len(cached) == 1
    # Verify cached records are tagged production_cached
    assert cached[0].data_origin == "production_cached"
    assert cached[0].arrival_date == "2026-09-20"
    assert cached[0].modal_price == 1950.0

    # Clean up
    db.query(MandiPrice).filter(MandiPrice.commodity == "TestBarley").delete()
    db.commit()
    db.close()


@pytest.mark.asyncio
async def test_upstream_provider_failure_fallback_to_cache():
    db = SessionLocal()
    provider = AgmarknetMandiProvider(db=db, api_key="dummy_key")

    # Insert a verified record into cache
    db.query(MandiPrice).filter(MandiPrice.commodity == "TestSoyabean").delete()
    db.commit()

    mandi_row = MandiPrice(
        state="Maharashtra",
        district="Latur",
        market="Latur",
        commodity="TestSoyabean",
        variety="Yellow",
        grade="FAQ",
        arrival_date=date(2026, 9, 21),
        min_price=4100.0,
        max_price=4600.0,
        modal_price=4450.0,
        source="Agmarknet",
        data_origin="production_live",
        fetched_at=datetime.now(timezone.utc),
    )
    db.add(mandi_row)
    db.commit()

    # Simulate upstream API HTTP 503 error
    with patch("httpx.AsyncClient.get", side_effect=Exception("Upstream connection timeout")):
        records = await provider.get_prices(state="Maharashtra", commodity="TestSoyabean")

        # Must fall back gracefully to cached record with production_cached tag
        assert len(records) == 1
        assert records[0].data_origin == "production_cached"
        assert records[0].modal_price == 4450.0
        assert records[0].arrival_date == "2026-09-21"

    # Clean up
    db.query(MandiPrice).filter(MandiPrice.commodity == "TestSoyabean").delete()
    db.commit()
    db.close()


@pytest.mark.asyncio
async def test_unavailable_upstream_and_no_cache():
    db = SessionLocal()
    provider = AgmarknetMandiProvider(db=db, api_key="dummy_key")

    with patch("httpx.AsyncClient.get", side_effect=Exception("API Down")):
        records = await provider.get_prices(state="NonExistentState", commodity="NonExistentCrop")
        # Should return empty result and never invent prices
        assert records == []
    db.close()
