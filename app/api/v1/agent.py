"""Research agent endpoints."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.agents.orchestrator import ResearchOrchestrator
from app.models.schemas import (
    CompanyIdentifier,
    JobResponse,
    JobStatus,
    ResearchDepth,
    ResearchRequest,
)

router = APIRouter(prefix="/research", tags=["Research Agent"])

# Singleton orchestrator (in-memory jobs – suitable for single instance)
_orchestrator: Optional[ResearchOrchestrator] = None


def get_orchestrator() -> ResearchOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = ResearchOrchestrator()
    return _orchestrator


@router.post("/run/sync", response_model=JobResponse)
async def run_sync(request: ResearchRequest):
    """
    Chạy phân tích đồng bộ – trả về báo cáo đầy đủ khi xong.
    Phù hợp depth=quick hoặc standard với timeout đủ lớn.
    """
    orch = get_orchestrator()
    job_id = orch.create_job(request.query, request.company)
    job = orch.run(
        query=request.query,
        job_id=job_id,
        company=request.company,
        depth=request.depth,
        include_macro=request.include_macro,
        export_pdf=request.export_pdf,
        export_excel=request.export_excel,
    )
    return JobResponse(
        job_id=job["job_id"],
        status=job["status"],
        message=job["message"],
        created_at=job["created_at"],
        updated_at=job["updated_at"],
        progress=job.get("progress", []),
        result=job.get("result"),
        error=job.get("error"),
    )


@router.post("/run", response_model=JobResponse)
async def run_async(request: ResearchRequest, background_tasks: BackgroundTasks):
    """Tạo job nền – poll /jobs/{job_id} để lấy kết quả."""
    orch = get_orchestrator()
    job_id = orch.create_job(request.query, request.company)

    def _bg():
        orch.run(
            query=request.query,
            job_id=job_id,
            company=request.company,
            depth=request.depth,
            include_macro=request.include_macro,
            export_pdf=request.export_pdf,
            export_excel=request.export_excel,
        )

    background_tasks.add_task(_bg)
    job = orch.get_job(job_id)
    return JobResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        message="Job queued",
        created_at=job["created_at"],
        updated_at=job["updated_at"],
        progress=[],
        result=None,
        error=None,
    )


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str):
    orch = get_orchestrator()
    job = orch.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse(
        job_id=job["job_id"],
        status=job["status"],
        message=job["message"],
        created_at=job["created_at"],
        updated_at=job["updated_at"],
        progress=job.get("progress", []),
        result=job.get("result"),
        error=job.get("error"),
    )
