from typing import List, Optional
from pydantic import BaseModel
from backend.app.providers.base import MandiPriceDTO


class MandiPricesResponse(BaseModel):
    total: int
    page: int
    page_size: int
    query_state: str
    query_district: Optional[str] = None
    query_commodity: Optional[str] = None
    records: List[MandiPriceDTO]
