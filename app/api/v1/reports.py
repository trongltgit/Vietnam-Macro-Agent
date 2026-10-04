"""Download generated research reports (PDF / MD / XLSX)."""

from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.config import get_settings

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/list")
async def list_reports():
    settings = get_settings()
    files: List[dict] = []
    folder = settings.reports_dir
    if folder.exists():
        for f in sorted(folder.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if f.is_file():
                files.append({
                    "filename": f.name,
                    "size_bytes": f.stat().st_size,
                    "suffix": f.suffix,
                    "download": f"/api/v1/reports/download/{f.name}",
                })
    return {"count": len(files), "files": files}


@router.get("/download/{filename}")
async def download_report(filename: str):
    settings = get_settings()
    # Security: only allow files inside reports_dir, no path traversal
    safe = Path(filename).name
    path = settings.reports_dir / safe
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    media = {
        ".pdf": "application/pdf",
        ".md": "text/markdown",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".csv": "text/csv",
        ".txt": "text/plain",
    }.get(path.suffix.lower())
    return FileResponse(path, filename=safe, media_type=media)
