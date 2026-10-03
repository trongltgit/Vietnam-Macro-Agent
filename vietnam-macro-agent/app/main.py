"""
Vietnam Macro AI Agent - FastAPI application entry point.
Production-ready API for collecting & analyzing Vietnamese macro reports.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import agent, analysis, health, reports
from app.core.config import get_settings
from app.core.logging import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info(
        "app_startup",
        name=settings.app_name,
        version=settings.app_version,
        env=settings.app_env,
    )
    # Ensure directories
    settings.ensure_directories()
    # Warm up LLM provider
    try:
        from app.llm.provider import get_llm_provider
        get_llm_provider()
        logger.info("llm_provider_ready")
    except Exception as e:
        logger.error("llm_provider_init_failed", error=str(e))
    yield
    logger.info("app_shutdown")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Professional AI Agent API for collecting official Vietnamese "
            "macroeconomic reports (NHNN, NSO) and correlating with internal Excel data."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Restrict in production if needed
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(agent.router, prefix="/api/v1")
    app.include_router(reports.router, prefix="/api/v1")
    app.include_router(analysis.router, prefix="/api/v1")

    @app.get("/")
    async def root():
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs",
            "health": "/api/v1/health",
        }

    return app


app = create_app()
