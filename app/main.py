"""
Vietnam Research Agent – Professional Macro & Corporate Analysis Platform
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup", version=settings.app_version, env=settings.environment)
    settings.ensure_dirs()
    yield
    logger.info("shutdown")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Nền tảng phân tích vĩ mô & doanh nghiệp Việt Nam chuyên sâu. "
        "Hỗ trợ mọi công ty (niêm yết & chưa niêm yết), xuất PDF research note chuẩn ngân hàng."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/", response_class=HTMLResponse)
async def ui():
    html_path = Path(__file__).parent / "templates" / "ui.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text(encoding="utf-8"))
    return HTMLResponse(
        """
        <html><head><title>Vietnam Research Agent</title></head>
        <body style="font-family:system-ui;max-width:800px;margin:40px auto;padding:0 20px">
          <h1>Vietnam Research Agent v2</h1>
          <p>Professional Macro & Corporate Research Platform</p>
          <ul>
            <li><a href="/docs">API Docs (Swagger)</a></li>
            <li><a href="/api/v1/health">Health</a></li>
            <li><a href="/api/v1/reports/list">Danh sách báo cáo</a></li>
          </ul>
          <h3>Ví dụ gọi API</h3>
          <pre style="background:#f4f4f4;padding:12px;border-radius:6px">
POST /api/v1/research/run/sync
{
  "query": "Phân tích sâu Vinamilk 2024-2025",
  "company": {"name": "Vinamilk", "ticker": "VNM"},
  "depth": "standard",
  "export_pdf": true
}
          </pre>
        </body></html>
        """
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
