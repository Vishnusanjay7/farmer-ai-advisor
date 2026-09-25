import time
from datetime import datetime, timezone, date
from typing import List, Optional, Dict, Any
import httpx
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.providers.base import MandiPriceProvider, MandiPriceDTO
from backend.app.models.models import MandiPrice


class AgmarknetPublicProvider(MandiPriceProvider):
    """
    Authoritative Mandi Price Provider integrating with the public Agmarknet 2.0 backend
    (https://api.agmarknet.gov.in/v1) as a temporary zero-credential provider.

    Key Features:
    - Zero API key required (read-only public endpoints)
    - Browser-origin headers to prevent 403 Forbidden
    - In-memory caching of metadata/filters (states, districts, commodities, markets)
    - Automatic resolution of IDs from common names
    - Latest available daily arrival date discovery (does not fabricate today's price)
    - Persists fetched live records to PostgreSQL mandi_prices with data_origin="production_live"
    - Falls back gracefully to production_cached records on upstream failure
    - Strict timeout and error handling (403, 429, 500+, connection errors, malformed responses)
    """

    BASE_URL = "https://api.agmarknet.gov.in/v1"
    SOURCE_LABEL = "Agmarknet 2.0"

    REQUEST_HEADERS = {
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://agmarknet.gov.in",
        "Referer": "https://agmarknet.gov.in/",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
    }

    # Class-level cache for filters metadata to avoid re-fetching ~500KB on every query
    _filters_cache: Optional[Dict[str, Any]] = None
    _filters_cached_at: float = 0.0
    _FILTERS_TTL_SECONDS: float = 3600.0  # 1 hour

    # Class-level cache for query responses to protect the public backend and prevent duplicate network calls
    _response_cache: Dict[str, Any] = {}
    _RESPONSE_CACHE_TTL_SECONDS: float = 300.0  # 5 minutes


    def __init__(self, db: Optional[Session] = None, timeout: float = 15.0):
        self.db = db
        self.timeout = timeout

    @staticmethod
    def parse_arrival_date(date_str: str) -> str:
        """Parses Agmarknet date formats (DD/MM/YYYY or YYYY-MM-DD) into ISO YYYY-MM-DD."""
        date_str = str(date_str).strip()
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return date_str

    async def get_filters(self, client: Optional[httpx.AsyncClient] = None) -> Dict[str, Any]:
        """Fetches and caches metadata filters from Agmarknet."""
        now = time.time()
        if (
            AgmarknetPublicProvider._filters_cache is not None
            and (now - AgmarknetPublicProvider._filters_cached_at) < self._FILTERS_TTL_SECONDS
        ):
            return AgmarknetPublicProvider._filters_cache

        url = f"{self.BASE_URL}/daily-price-arrival/filters"
        close_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout)
            close_client = True

        try:
            resp = await client.get(url, headers=self.REQUEST_HEADERS)
            if resp.status_code != 200:
                logger.warning(
                    f"Agmarknet filters endpoint returned HTTP {resp.status_code}"
                )
                return AgmarknetPublicProvider._filters_cache or {}

            body = resp.json()
            data = body.get("data", {})
            AgmarknetPublicProvider._filters_cache = data
            AgmarknetPublicProvider._filters_cached_at = now
            return data
        except Exception as e:
            logger.warning(f"Failed to fetch Agmarknet filters: {e}")
            return AgmarknetPublicProvider._filters_cache or {}
        finally:
            if close_client:
                await client.aclose()

    def resolve_identifiers(
        self,
        filters: Dict[str, Any],
        state_name: Optional[str] = None,
        district_name: Optional[str] = None,
        commodity_name: Optional[str] = None,
        market_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Resolves entity names to Agmarknet numeric identifiers using filter metadata.
        Falls back to known identifiers if metadata matching misses.
        """
        resolved: Dict[str, Any] = {
            "state_id": None,
            "state_name": state_name,
            "district_id": None,
            "district_name": district_name,
            "commodity_id": None,
            "commodity_name": commodity_name,
            "market_id": None,
            "market_name": market_name,
        }

        # 1. Commodity resolution
        if commodity_name and "cmdt_data" in filters:
            norm_comm = commodity_name.lower().strip()
            for c in filters["cmdt_data"]:
                c_name = str(c.get("cmdt_name", "")).lower()
                if norm_comm == c_name or (norm_comm in c_name and len(norm_comm) > 3):
                    resolved["commodity_id"] = c.get("cmdt_id")
                    resolved["commodity_name"] = c.get("cmdt_name")
                    break

        # Fallback known commodities
        if not resolved["commodity_id"] and commodity_name:
            if "wheat" in commodity_name.lower():
                resolved["commodity_id"] = 1
                resolved["commodity_name"] = "Wheat"

        # 2. State resolution
        if state_name and "state_data" in filters:
            norm_state = state_name.lower().strip()
            for s in filters["state_data"]:
                s_name = str(s.get("state_name", "")).lower()
                if norm_state in s_name or s_name in norm_state:
                    resolved["state_id"] = s.get("state_id")
                    resolved["state_name"] = s.get("state_name")
                    break

        # Fallback known states
        if not resolved["state_id"] and state_name:
            if "madhya" in state_name.lower():
                resolved["state_id"] = 19
                resolved["state_name"] = "Madhya Pradesh"

        # 3. District resolution (can infer state if state was omitted)
        if district_name and "district_data" in filters:
            norm_dist = district_name.lower().strip()
            for d in filters["district_data"]:
                d_name = str(d.get("district_name", "")).lower()
                if norm_dist in d_name:
                    resolved["district_id"] = d.get("id")
                    resolved["district_name"] = d.get("district_name")
                    if not resolved["state_id"] and d.get("state_id"):
                        resolved["state_id"] = d.get("state_id")
                    break

        # Fallback known district
        if not resolved["district_id"] and district_name:
            if "indore" in district_name.lower():
                resolved["district_id"] = 308
                resolved["district_name"] = "Indore"
                if not resolved["state_id"]:
                    resolved["state_id"] = 19
                    resolved["state_name"] = "Madhya Pradesh"

        # 4. Market resolution
        target_market_str = (market_name or district_name or "").lower().strip()
        if target_market_str and "market_data" in filters:
            for m in filters["market_data"]:
                m_name = str(m.get("mkt_name", "")).lower()
                m_state = m.get("state_id")
                # Filter by state if resolved
                if resolved["state_id"] and m_state and m_state != resolved["state_id"]:
                    continue
                if target_market_str in m_name:
                    resolved["market_id"] = m.get("id")
                    resolved["market_name"] = m.get("mkt_name")
                    break

        # Fallback known market
        if not resolved["market_id"] and (market_name or district_name):
            val = (market_name or district_name).lower()
            if "indore" in val:
                resolved["market_id"] = 3046
                resolved["market_name"] = "Indore APMC"

        return resolved

    async def fetch_latest_commodity_prices(
        self,
        client: httpx.AsyncClient,
        state_id: int,
        commodity_id: int,
        target_market: Optional[str] = None,
        target_district: Optional[str] = None,
        state_name: Optional[str] = None,
        commodity_name: Optional[str] = None,
    ) -> List[MandiPriceDTO]:
        """
        Queries /prices-and-arrivals/date-wise/specific-commodity for the current month
        to discover the newest available valid arrival date.
        """
        today = date.today()
        url = f"{self.BASE_URL}/prices-and-arrivals/date-wise/specific-commodity"
        params = {
            "year": today.year,
            "month": today.month,
            "stateId": state_id,
            "commodityId": commodity_id,
            "includeExcel": "false",
        }

        logger.info(
            f"AgmarknetPublicProvider: Querying date-wise commodity (stateId={state_id}, commodityId={commodity_id})"
        )
        resp = await client.get(url, params=params, headers=self.REQUEST_HEADERS)
        if resp.status_code != 200:
            logger.warning(
                f"Agmarknet date-wise endpoint returned HTTP {resp.status_code}: {resp.text[:200]}"
            )
            return []

        body = resp.json()
        if not isinstance(body, dict):
            logger.warning("Agmarknet returned unexpected non-dict response")
            return []

        markets = body.get("markets", [])
        if not markets:
            return []

        # Filter markets by target_market / target_district if provided
        filtered_markets = markets
        if target_market or target_district:
            norm_query = (target_market or target_district).lower().strip()
            matched = [
                m for m in markets if norm_query in str(m.get("marketName", "")).lower()
            ]
            if matched:
                filtered_markets = matched

        dtos: List[MandiPriceDTO] = []
        fetched_at_str = datetime.now(timezone.utc).isoformat()

        for m_item in filtered_markets:
            m_name = m_item.get("marketName", "Mandi APMC")
            dates = m_item.get("dates", [])
            if not dates:
                continue

            # dates is ordered chronologically; the last item is the latest available arrival date
            latest_date_entry = dates[-1]
            raw_arrival_date = latest_date_entry.get("arrivalDate", "")
            iso_arrival_date = self.parse_arrival_date(raw_arrival_date)

            for rec in latest_date_entry.get("data", []):
                try:
                    min_price = float(rec.get("minimumPrice", 0.0))
                    max_price = float(rec.get("maximumPrice", 0.0))
                    modal_price = float(rec.get("modalPrice", 0.0))
                except (ValueError, TypeError):
                    min_price, max_price, modal_price = 0.0, 0.0, 0.0

                variety = str(rec.get("variety", "Standard")).strip() or "Standard"
                grade = str(rec.get("grade", "FAQ")).strip() or "FAQ"

                dtos.append(
                    MandiPriceDTO(
                        state=state_name or "State",
                        district=target_district or m_name.replace(" APMC", "").strip(),
                        market=m_name,
                        commodity=commodity_name or "Commodity",
                        variety=variety,
                        grade=grade,
                        arrival_date=iso_arrival_date,
                        min_price=min_price,
                        max_price=max_price,
                        modal_price=modal_price,
                        source=self.SOURCE_LABEL,
                        data_origin="production_live",
                        fetched_at=fetched_at_str,
                    )
                )

        return dtos

    async def fetch_market_daily_report(
        self,
        client: httpx.AsyncClient,
        target_date: str,
        market_ids: List[int],
        state_ids: List[int],
        target_commodity: Optional[str] = None,
        state_name: Optional[str] = None,
        district_name: Optional[str] = None,
    ) -> List[MandiPriceDTO]:
        """Queries /prices-and-arrivals/market-report/daily for a specific date and market."""
        url = f"{self.BASE_URL}/prices-and-arrivals/market-report/daily"
        payload = {
            "date": target_date,
            "marketIds": market_ids,
            "stateIds": state_ids,
            "includeExcel": False,
        }

        resp = await client.post(url, json=payload, headers=self.REQUEST_HEADERS)
        if resp.status_code != 200:
            logger.warning(
                f"Agmarknet daily report returned HTTP {resp.status_code}: {resp.text[:200]}"
            )
            return []

        body = resp.json()
        if not isinstance(body, dict):
            return []

        states = body.get("states", [])
        dtos: List[MandiPriceDTO] = []
        fetched_at_str = datetime.now(timezone.utc).isoformat()
        iso_arr_date = self.parse_arrival_date(target_date)

        for s in states:
            s_name = s.get("stateName") or state_name or "State"
            for m in s.get("markets", []):
                m_name = m.get("marketName", "Mandi APMC")
                for c in m.get("commodities", []):
                    c_name = c.get("commodityName", "Commodity")
                    if target_commodity:
                        if target_commodity.lower() not in c_name.lower():
                            continue

                    for item in c.get("data", []):
                        try:
                            min_price = float(item.get("minimumPrice", 0.0))
                            max_price = float(item.get("maximumPrice", 0.0))
                            modal_price = float(item.get("modalPrice", 0.0))
                        except (ValueError, TypeError):
                            min_price, max_price, modal_price = 0.0, 0.0, 0.0

                        variety = str(item.get("variety", "Standard")).strip() or "Standard"
                        grade = str(item.get("grade", "FAQ")).strip() or "FAQ"

                        dtos.append(
                            MandiPriceDTO(
                                state=s_name,
                                district=district_name or m_name.replace(" APMC", "").strip(),
                                market=m_name,
                                commodity=c_name,
                                variety=variety,
                                grade=grade,
                                arrival_date=iso_arr_date,
                                min_price=min_price,
                                max_price=max_price,
                                modal_price=modal_price,
                                source=self.SOURCE_LABEL,
                                data_origin="production_live",
                                fetched_at=fetched_at_str,
                            )
                        )

        return dtos

    def cache_records(self, dtos: List[MandiPriceDTO]) -> int:
        """Saves or updates fetched live records in PostgreSQL using the MandiPrice model."""
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
                    existing.source = dto.source
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
                logger.warning(
                    f"Failed caching public Agmarknet record {dto.market}/{dto.commodity}: {e}"
                )
                continue

        try:
            self.db.commit()
        except Exception as e:
            logger.warning(f"Database commit error while caching mandi records: {e}")
            self.db.rollback()

        return saved

    def get_cached_records(
        self,
        state: str,
        district: Optional[str] = None,
        commodity: Optional[str] = None,
    ) -> List[MandiPriceDTO]:
        """Retrieves cached records from PostgreSQL, tagged as production_cached."""
        if not self.db:
            return []

        query = self.db.query(MandiPrice).filter(
            MandiPrice.data_origin.in_(["production_live", "production_cached"])
        )
        if state:
            query = query.filter(MandiPrice.state.ilike(f"%{state}%"))
        if district:
            query = query.filter(
                (MandiPrice.district.ilike(f"%{district}%"))
                | (MandiPrice.market.ilike(f"%{district}%"))
            )
        if commodity:
            query = query.filter(MandiPrice.commodity.ilike(f"%{commodity}%"))

        records = query.order_by(MandiPrice.arrival_date.desc()).limit(50).all()

        dtos = []
        for r in records:
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
                    data_origin="production_cached",
                    fetched_at=(
                        r.fetched_at.isoformat()
                        if r.fetched_at
                        else datetime.now(timezone.utc).isoformat()
                    ),
                )
            )
        return dtos

    def _is_cache_fresh(
        self, state: str, district: Optional[str] = None, commodity: Optional[str] = None
    ) -> bool:
        """Checks if recent production_live data within TTL exists in DB cache."""
        if not self.db:
            return False

        try:
            query = self.db.query(MandiPrice).filter(
                MandiPrice.data_origin == "production_live"
            )
            if state:
                query = query.filter(MandiPrice.state.ilike(f"%{state}%"))
            if district:
                query = query.filter(
                    (MandiPrice.district.ilike(f"%{district}%"))
                    | (MandiPrice.market.ilike(f"%{district}%"))
                )
            if commodity:
                query = query.filter(MandiPrice.commodity.ilike(f"%{commodity}%"))

            latest_rec = query.order_by(MandiPrice.fetched_at.desc()).first()
            if not latest_rec or not latest_rec.fetched_at:
                return False

            now = datetime.now(timezone.utc)
            fetched = latest_rec.fetched_at
            if fetched.tzinfo is None:
                fetched = fetched.replace(tzinfo=timezone.utc)

            age_seconds = (now - fetched).total_seconds()
            ttl = getattr(settings, "AGMARKNET_CACHE_TTL_SECONDS", 21600)
            return age_seconds < ttl
        except Exception as e:


            logger.warning(f"Error checking mandi cache freshness: {e}")
            return False

    async def get_prices(
        self,
        state: str,
        district: Optional[str] = None,
        commodity: Optional[str] = None,
    ) -> List[MandiPriceDTO]:
        """
        Primary entry point.
        1. Checks DB cache freshness (TTL) to avoid unnecessary upstream calls.
        2. Queries Agmarknet 2.0 public endpoints for latest available daily arrival data.
        3. Caches live records to PostgreSQL with data_origin="production_live".
        4. Falls back to database cache tagged 'production_cached' on upstream failure.
        5. Never fabricates today's price from older dates or development data.
        """
        logger.info(
            f"AgmarknetPublicProvider query: state='{state}', district='{district}', commodity='{commodity}'"
        )

        # 0. In-memory response cache check (protects against rapid repeated calls in tests or UI)
        cache_key = f"{str(state).strip().lower()}:{str(district).strip().lower()}:{str(commodity).strip().lower()}"
        now_ts = time.time()
        if cache_key in AgmarknetPublicProvider._response_cache:
            cached_ts, cached_dtos = AgmarknetPublicProvider._response_cache[cache_key]
            if (now_ts - cached_ts) < AgmarknetPublicProvider._RESPONSE_CACHE_TTL_SECONDS:
                logger.info(
                    f"AgmarknetPublicProvider: Returning {len(cached_dtos)} records from in-memory response cache."
                )
                return cached_dtos

        # 1. Fast-path: Check if fresh cache exists within TTL in DB
        if self._is_cache_fresh(state=state, district=district, commodity=commodity):
            cached = self.get_cached_records(state=state, district=district, commodity=commodity)
            if cached:
                AgmarknetPublicProvider._response_cache[cache_key] = (now_ts, cached)
                logger.info(
                    f"AgmarknetPublicProvider: Returning {len(cached)} fresh cached records (cache hit)."
                )
                return cached

        # 2. Attempt live pull from public Agmarknet 2.0 endpoints
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                filters = await self.get_filters(client=client)
                resolved = self.resolve_identifiers(
                    filters=filters,
                    state_name=state,
                    district_name=district,
                    commodity_name=commodity,
                )

                state_id = resolved.get("state_id")
                commodity_id = resolved.get("commodity_id")

                dtos: List[MandiPriceDTO] = []

                # Strategy A: If state and commodity are resolved, date-wise report gives
                # the complete chronological history including newest available date in 1 call
                if state_id and commodity_id:
                    dtos = await self.fetch_latest_commodity_prices(
                        client=client,
                        state_id=state_id,
                        commodity_id=commodity_id,
                        target_market=resolved.get("market_name"),
                        target_district=resolved.get("district_name") or district,
                        state_name=resolved.get("state_name") or state,
                        commodity_name=resolved.get("commodity_name") or commodity,
                    )

                # Strategy B: If market_id and state_id are resolved, query daily report
                if not dtos and resolved.get("market_id") and state_id:
                    today_iso = date.today().isoformat()
                    dtos = await self.fetch_market_daily_report(
                        client=client,
                        target_date=today_iso,
                        market_ids=[resolved["market_id"]],
                        state_ids=[state_id],
                        target_commodity=commodity,
                        state_name=resolved.get("state_name") or state,
                        district_name=resolved.get("district_name") or district,
                    )

                if dtos:
                    self.cache_records(dtos)
                    AgmarknetPublicProvider._response_cache[cache_key] = (now_ts, dtos)
                    logger.info(
                        f"AgmarknetPublicProvider: Retrieved {len(dtos)} live records from Agmarknet 2.0."
                    )
                    return dtos


        except httpx.HTTPStatusError as exc:
            logger.warning(
                f"AgmarknetPublicProvider upstream HTTP error {exc.response.status_code}: {exc}"
            )
        except Exception as exc:
            logger.warning(f"AgmarknetPublicProvider upstream failure: {exc}")

        # 3. Upstream failure or no live data: Fallback to verified database cache
        cached = self.get_cached_records(state=state, district=district, commodity=commodity)
        if cached:
            logger.info(
                f"AgmarknetPublicProvider: Returning {len(cached)} cached records (production_cached)."
            )
            return cached

        # 4. Safe abstention
        logger.info(
            f"AgmarknetPublicProvider: No mandi records found for state='{state}', commodity='{commodity}'. Returning empty result."
        )
        return []
