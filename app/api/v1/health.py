from datetime import datetime

from fastapi import APIRouter

from app.core.config import get_settings
from app.llm.provider import get_llm_provider
from app.models.schemas import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
async def health():
    settings = get_settings()
    try:
        llm = get_llm_provider()
        llm_status = llm.status()
    except Exception as e:
        llm_status = {"ready": False, "error": str(e)}

    return HealthResponse(
        status="ok",
        version=settings.app_version,
        environment=settings.environment,
        llm_status=llm_status,
        timestamp=datetime.utcnow(),
    )
