from typing import List, Optional, Dict
from pydantic import BaseModel


class SchemeDetailResponse(BaseModel):
    id: str
    scheme_code: str
    scheme_name: str
    name_translations: Dict[str, str] = {}
    short_description: str
    benefits_summary: str
    eligibility_criteria: List[str] = []
    required_documents: List[str] = []
    application_process: str
    official_portal_url: str
    sponsoring_agency: str
    state_scope: str
    last_verified_date: str
    is_active: bool = True


class SchemeSearchResponse(BaseModel):
    total: int
    page: int
    page_size: int
    schemes: List[SchemeDetailResponse]
