from fastapi import APIRouter

from app.api.v1.agent import router as agent_router
from app.api.v1.health import router as health_router
from app.api.v1.reports import router as reports_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(agent_router)
api_router.include_router(reports_router)
