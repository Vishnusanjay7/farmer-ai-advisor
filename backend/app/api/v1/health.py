from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional

from backend.app.schemas.health import HealthResponse
from backend.app.core.config import settings
from backend.app.db.session import get_db

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
async def get_health(db: Session = Depends(get_db)) -> HealthResponse:
    """Returns the operational status of the Farmer AI backend service and safe database connectivity."""
    db_status = "connected"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_status = "disconnected"

    return HealthResponse(
        status="ok",
        service="farmer-ai-backend",
        version=settings.APP_VERSION,
        database=db_status,
        environment=settings.ENVIRONMENT,
    )
