from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.providers.mandi_provider import AgmarknetMandiProvider
from backend.app.schemas.mandi import MandiPricesResponse

router = APIRouter(prefix="/mandi", tags=["Mandi Prices"])


@router.get("/prices", response_model=MandiPricesResponse)
async def get_mandi_prices(
    state: str = Query(..., min_length=2, description="Target state (e.g. 'Uttar Pradesh', 'Madhya Pradesh')"),
    district: Optional[str] = Query(None, description="Optional target district (e.g. 'Indore')"),
    commodity: Optional[str] = Query(None, description="Optional target commodity (e.g. 'Wheat', 'Soyabean')"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Records per page"),
    db: Session = Depends(get_db),
) -> MandiPricesResponse:
    """
    Fetches market prices from authoritative sources (Data.gov.in / Agmarknet).
    Falls back to cached authoritative records on upstream failure.
    Records clearly specify arrival_date and data_origin ('production_live', 'production_cached', 'development_seed').
    """
    provider = AgmarknetMandiProvider(db=db)
    records = await provider.get_prices(state=state, district=district, commodity=commodity)

    total = len(records)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated = records[start_idx:end_idx]

    return MandiPricesResponse(
        total=total,
        page=page,
        page_size=page_size,
        query_state=state,
        query_district=district,
        query_commodity=commodity,
        records=paginated,
    )
