from datetime import datetime

from fastapi import APIRouter

from app.core.config import get_settings
from app.models.schemas import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    settings = get_settings()
    llm_status = {"initialized": False}
    try:
        if settings.groq_api_key:
            from app.llm.provider import get_llm_provider
            llm_status = get_llm_provider().get_status()
            llm_status["initialized"] = True
        else:
            llm_status = {"error": "GROQ_API_KEY not set", "initialized": False}
    except Exception as e:
        llm_status = {"error": str(e), "initialized": False}

    return HealthResponse(
        status="ok",
        version=settings.app_version,
        environment=settings.app_env,
        llm_status=llm_status,
        timestamp=datetime.utcnow(),
    )
