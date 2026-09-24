from typing import Optional
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "farmer-ai-backend"
    version: str = "0.1.0"
    database: Optional[str] = None
    environment: Optional[str] = None
