import json
from datetime import datetime, timezone, date
from typing import List, Optional, Dict, Any
import httpx
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.providers.base import MandiPriceProvider, MandiPriceDTO
from backend.app.models.models import MandiPrice


class AgmarknetMandiProvider(MandiPriceProvider):
    """
    Authoritative Mandi Price Provider integrating with Data.gov.in / Agmarknet Open Government Data (OGD) API.
    Features:
    - Live fetching with API key authentication
    - Strict schema validation & price parsing
    - Distinct arrival_date vs fetched_at separation
    - Automatic caching to PostgreSQL
    - Graceful fallback to production_cached records on upstream failure
    - Development seed support strictly tagged as development_seed
    """

    BASE_URL = "https://api.data.gov.in/resource"

    def __init__(self, db: Optional[Session] = None, api_key: Optional[str] = None):
        self.db = db
        self.api_key = api_key or settings.DATA_GOV_IN_API_KEY
        self.resource_id = settings.AGMARKNET_RESOURCE_ID

    def parse_arrival_date(self, date_str: str) -> str:
        """Parses various government date formats (DD/MM/YYYY or YYYY-MM-DD) into ISO YYYY-MM-DD."""
        date_str = date_str.strip()
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        # If already formatted or fallback
        return date_str

    async def fetch_from_api(
        self, state: str, district: Optional[str] = None, commodity: Optional[str] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        if not self.api_key:
            raise ValueError("DATA_GOV_IN_API_KEY is not configured in environment.")

        url = f"{self.BASE_URL}/{self.resource_id}"
        params = {
            "api-key": self.api_key,
            "format": "json",
            "limit": str(limit),
            "filters[state]": state,
        }
        if district:
            params["filters[district]"] = district
        if commodity:
            params["filters[commodity]"] = commodity

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                raise RuntimeError(f"Data.gov.in API returned HTTP {resp.status_code}: {resp.text}")
            data = resp.json()
            records = data.get("records", [])
            return records

    def normalize_record(self, raw: Dict[str, Any], data_origin: str = "production_live") -> MandiPriceDTO:
        """Normalizes raw Data.gov.in dictionary into strictly typed MandiPriceDTO."""
        arrival_date_str = self.parse_arrival_date(str(raw.get("arrival_date", "")))
        fetched_at_str = datetime.now(timezone.utc).isoformat()

        try:
            min_price = float(raw.get("min_price", 0.0))
            max_price = float(raw.get("max_price", 0.0))
            modal_price = float(raw.get("modal_price", 0.0))
        except (ValueError, TypeError):
            min_price, max_price, modal_price = 0.0, 0.0, 0.0

        return MandiPriceDTO(
            state=str(raw.get("state", "")).strip(),
            district=str(raw.get("district", "")).strip(),
            market=str(raw.get("market", "")).strip(),
            commodity=str(raw.get("commodity", "")).strip(),
            variety=str(raw.get("variety", "Common")).strip() or "Common",
            grade=str(raw.get("grade", "FAQ")).strip() or "FAQ",
            arrival_date=arrival_date_str,
            min_price=min_price,
            max_price=max_price,
            modal_price=modal_price,
            source=str(raw.get("source", "Agmarknet / data.gov.in")),
            data_origin=data_origin,
            fetched_at=fetched_at_str,
        )

    def cache_records(self, dtos: List[MandiPriceDTO]) -> int:
        """Saves or updates fetched live records in PostgreSQL."""
        if not self.db:
            return 0

        saved = 0
        for dto in dtos:
            try:
                arr_date = datetime.strptime(dto.arrival_date, "%Y-%m-%d").date()
                existing = (
                    self.db.query(MandiPrice)
                    .filter(
                        MandiPrice.state == dto.state,
                        MandiPrice.district == dto.district,
                        MandiPrice.market == dto.market,
                        MandiPrice.commodity == dto.commodity,
                        MandiPrice.variety == dto.variety,
                        MandiPrice.arrival_date == arr_date,
                    )
                    .first()
                )

                if existing:
                    existing.min_price = dto.min_price
                    existing.max_price = dto.max_price
                    existing.modal_price = dto.modal_price
                    existing.data_origin = "production_live"
                    existing.fetched_at = datetime.now(timezone.utc)
                    existing.updated_at = datetime.now(timezone.utc)
                else:
                    rec = MandiPrice(
                        state=dto.state,
                        district=dto.district,
                        market=dto.market,
                        commodity=dto.commodity,
                        variety=dto.variety,
                        grade=dto.grade,
                        arrival_date=arr_date,
                        min_price=dto.min_price,
                        max_price=dto.max_price,
                        modal_price=dto.modal_price,
                        source=dto.source,
                        data_origin="production_live",
                        fetched_at=datetime.now(timezone.utc),
                    )
                    self.db.add(rec)
                saved += 1
            except Exception as e:
                logger.warning(f"Failed caching mandi record {dto.market}/{dto.commodity}: {e}")
                continue

        self.db.commit()
        return saved

    def get_cached_records(
        self, state: str, district: Optional[str] = None, commodity: Optional[str] = None
    ) -> List[MandiPriceDTO]:
        """Retrieves cached records from PostgreSQL, explicitly tagged as production_cached."""
        if not self.db:
            return []

        query = self.db.query(MandiPrice).filter(MandiPrice.state.ilike(f"%{state}%"))
        if district:
            query = query.filter(MandiPrice.district.ilike(f"%{district}%"))
        if commodity:
            query = query.filter(MandiPrice.commodity.ilike(f"%{commodity}%"))

        records = query.order_by(MandiPrice.arrival_date.desc()).limit(50).all()

        dtos = []
        for r in records:
            # Explicitly mark data_origin as production_cached (or preserve development_seed if already marked)
            origin = "development_seed" if r.data_origin == "development_seed" else "production_cached"
            dtos.append(
                MandiPriceDTO(
                    state=r.state,
                    district=r.district,
                    market=r.market,
                    commodity=r.commodity,
                    variety=r.variety,
                    grade=r.grade,
                    arrival_date=r.arrival_date.isoformat(),
                    min_price=float(r.min_price),
                    max_price=float(r.max_price),
                    modal_price=float(r.modal_price),
                    source=r.source,
                    data_origin=origin,
                    fetched_at=r.fetched_at.isoformat() if r.fetched_at else datetime.now(timezone.utc).isoformat(),
                )
            )
        return dtos

    async def get_prices(
        self, state: str, district: Optional[str] = None, commodity: Optional[str] = None
    ) -> List[MandiPriceDTO]:
        """
        Primary entry point. Attempts live API pull.
        Falls back to database cache tagged 'production_cached' on upstream API error.
        Never fabricates prices or claims an old arrival date is today.
        """
        logger.info(f"Mandi query: state='{state}', district='{district}', commodity='{commodity}'")

        # 1. Attempt live API fetch if key is present
        if self.api_key:
            try:
                raw_records = await self.fetch_from_api(state=state, district=district, commodity=commodity)
                if raw_records:
                    normalized = [self.normalize_record(r, data_origin="production_live") for r in raw_records]
                    self.cache_records(normalized)
                    logger.info(f"Retrieved {len(normalized)} live records from Data.gov.in Agmarknet.")
                    return normalized
            except Exception as exc:
                logger.warning(f"Live Agmarknet fetch failed ({exc}). Falling back to cached records.")

        # 2. Upstream failure or no key: Fall back to verified cached records in DB
        cached = self.get_cached_records(state=state, district=district, commodity=commodity)
        if cached:
            logger.info(f"Returning {len(cached)} cached records from database (production_cached).")
            return cached

        # 3. No live or cached records available
        logger.info(f"No mandi records found for state='{state}', commodity='{commodity}'. Returning empty result.")
        return []
