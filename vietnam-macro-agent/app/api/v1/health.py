from datetime import datetime

from fastapi import APIRouter

from app.core.config import get_settings
from app.llm.provider import get_llm_provider
from app.models.schemas import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    settings = get_settings()
    try:
        llm_status = get_llm_provider().get_status()
    except Exception as e:
        llm_status = {"error": str(e)}

    return HealthResponse(
        status="ok",
        version=settings.app_version,
        environment=settings.app_env,
        llm_status=llm_status,
        timestamp=datetime.utcnow(),
    )
