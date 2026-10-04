from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.config import get_settings
from app.extractors.pdf_extractor import PDFExtractor
from app.models.schemas import ExtractRequest

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/list")
async def list_downloaded_reports():
    """Liệt kê file raw (PDF đã tải) + file báo cáo đã xuất (md/csv/xlsx)."""
    settings = get_settings()
    files: List[dict] = []

    for sub in ["nhnn", "nso", "companies", "other"]:
        folder = settings.raw_dir / sub
        if not folder.exists():
            continue
        for f in folder.iterdir():
            if f.is_file():
                files.append({
                    "kind": "raw",
                    "subdir": sub,
                    "filename": f.name,
                    "path": str(f),
                    "size_bytes": f.stat().st_size,
                    "suffix": f.suffix,
                    "download": f"/api/v1/reports/download/{sub}/{f.name}",
                })

    reports_dir = settings.processed_dir / "reports"
    if reports_dir.exists():
        for f in sorted(reports_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if f.is_file():
                files.append({
                    "kind": "export",
                    "subdir": "reports",
                    "filename": f.name,
                    "path": str(f),
                    "size_bytes": f.stat().st_size,
                    "suffix": f.suffix,
                    "download": f"/api/v1/reports/download-processed/reports/{f.name}",
                })

    return {"count": len(files), "files": files}


@router.post("/extract")
async def extract_file(request: ExtractRequest):
    path = Path(request.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    if path.suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="Only PDF supported")
    extractor = PDFExtractor()
    try:
        result = extractor.extract(path)
        tables = []
        for t in result.get("tables", []):
            df = t.get("dataframe")
            tables.append({
                "page": t.get("page"),
                "table_index": t.get("table_index"),
                "shape": t.get("shape"),
                "preview": t.get("preview"),
                "columns": list(df.columns) if df is not None else [],
            })
        return {
            "status": "ok",
            "file": result["file"],
            "pages_processed": result["pages_processed"],
            "text_preview": result["text"][:3000],
            "text_chars": len(result["text"]),
            "tables": tables,
            "indicators": extractor.extract_key_indicators(result["text"]),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download/{subdir}/{filename}")
async def download_raw_file(subdir: str, filename: str):
    settings = get_settings()
    path = settings.raw_dir / subdir / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path, filename=filename)


@router.get("/download-processed/{subdir}/{filename}")
async def download_processed_file(subdir: str, filename: str):
    """Tải file đã xuất: báo cáo .md, chỉ số .csv / .xlsx trong data/processed/."""
    settings = get_settings()
    # only allow reports subdir for safety
    if subdir != "reports":
        raise HTTPException(status_code=400, detail="Only subdir=reports allowed")
    path = settings.processed_dir / subdir / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    media = "text/markdown" if path.suffix == ".md" else None
    return FileResponse(path, filename=filename, media_type=media)
