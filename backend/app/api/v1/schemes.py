from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_

from backend.app.db.session import get_db
from backend.app.models.models import GovernmentScheme
from backend.app.schemas.schemes import SchemeSearchResponse, SchemeDetailResponse

router = APIRouter(prefix="/schemes", tags=["Government Schemes"])


@router.get("/search", response_model=SchemeSearchResponse)
async def search_schemes(
    q: Optional[str] = Query(None, description="Search keyword (e.g., 'insurance', 'credit', 'irrigation')"),
    state: Optional[str] = Query(None, description="State filter or 'Central'"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=50, description="Page size"),
    db: Session = Depends(get_db),
) -> SchemeSearchResponse:
    """
    Searches authoritative government schemes with verified eligibility criteria,
    required documents, and official portal URLs.
    """
    query = db.query(GovernmentScheme).filter(GovernmentScheme.is_active == True)

    if q:
        search_pattern = f"%{q.strip()}%"
        query = query.filter(
            or_(
                GovernmentScheme.scheme_name.ilike(search_pattern),
                GovernmentScheme.scheme_code.ilike(search_pattern),
                GovernmentScheme.short_description.ilike(search_pattern),
                GovernmentScheme.benefits_summary.ilike(search_pattern),
            )
        )

    if state and state.lower() != "all":
        query = query.filter(
            or_(
                GovernmentScheme.state_scope.ilike(f"%{state}%"),
                GovernmentScheme.state_scope == "Central",
            )
        )

    total = query.count()
    offset = (page - 1) * page_size
    schemes = query.order_by(GovernmentScheme.scheme_name.asc()).offset(offset).limit(page_size).all()

    items = [
        SchemeDetailResponse(
            id=str(s.id),
            scheme_code=s.scheme_code,
            scheme_name=s.scheme_name,
            name_translations=s.name_translations or {},
            short_description=s.short_description,
            benefits_summary=s.benefits_summary,
            eligibility_criteria=s.eligibility_criteria or [],
            required_documents=s.required_documents or [],
            application_process=s.application_process,
            official_portal_url=s.official_portal_url,
            sponsoring_agency=s.sponsoring_agency,
            state_scope=s.state_scope,
            last_verified_date=s.last_verified_date.isoformat(),
            is_active=s.is_active,
        )
        for s in schemes
    ]

    return SchemeSearchResponse(
        total=total,
        page=page,
        page_size=page_size,
        schemes=items,
    )
