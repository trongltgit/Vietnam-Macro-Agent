"""
Vietnam Macro AI Agent - FastAPI entry + Web UI.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

from app.api.v1 import agent, analysis, health, reports
from app.core.config import get_settings
from app.core.logging import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"
UI_HTML = TEMPLATES_DIR / "ui.html"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info(
        "app_startup",
        name=settings.app_name,
        version=settings.app_version,
        env=settings.app_env,
        has_groq_key=bool(settings.groq_api_key),
    )
    settings.ensure_directories()
    # Do NOT block startup on LLM — init lazily on first request
    yield
    logger.info("app_shutdown")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="AI Agent for Vietnamese macro reports (NHNN, NSO)",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api/v1")
    app.include_router(agent.router, prefix="/api/v1")
    app.include_router(reports.router, prefix="/api/v1")
    app.include_router(analysis.router, prefix="/api/v1")

    @app.get("/ui", response_class=HTMLResponse)
    @app.get("/", response_class=HTMLResponse)
    async def web_ui():
        if UI_HTML.exists():
            return FileResponse(UI_HTML, media_type="text/html; charset=utf-8")
        return HTMLResponse("<h1>UI missing</h1>", status_code=404)

    @app.get("/api")
    async def api_info():
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs",
            "health": "/api/v1/health",
            "ui": "/",
        }

    return app


app = create_app()
