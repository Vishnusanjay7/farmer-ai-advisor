from fastapi import APIRouter
from backend.app.api.v1.health import router as health_router
from backend.app.api.v1.mandi import router as mandi_router
from backend.app.api.v1.schemes import router as schemes_router
from backend.app.api.v1.agriculture import router as agriculture_router
from backend.app.api.v1.voice import router as voice_router
from backend.app.api.v1.advisor import router as advisor_router
from backend.app.api.v1.conversations import router as conversations_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(health_router)
api_v1_router.include_router(mandi_router)
api_v1_router.include_router(schemes_router)
api_v1_router.include_router(agriculture_router)
api_v1_router.include_router(voice_router)
api_v1_router.include_router(advisor_router)
api_v1_router.include_router(conversations_router)

__all__ = ["api_v1_router"]

