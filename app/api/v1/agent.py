from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.agent.orchestrator import AgentOrchestrator
from app.models.schemas import AgentRunRequest, JobResponse, JobStatus

router = APIRouter(prefix="/agent", tags=["Agent"])

_orchestrator: Optional[AgentOrchestrator] = None


def get_orchestrator() -> AgentOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator()
    return _orchestrator


@router.post("/run", response_model=JobResponse)
async def run_agent(request: AgentRunRequest, background_tasks: BackgroundTasks):
    """
    Chạy agent với câu hỏi tự nhiên (+ optional mã CK).
    Job chạy nền, trả về job_id ngay. Dùng GET /agent/jobs/{job_id} để theo dõi.
    """
    orch = get_orchestrator()
    job_id = orch.create_job(request.query, ticker=request.ticker)

    def _run():
        orch.run(request.query, job_id=job_id, ticker=request.ticker)

    background_tasks.add_task(_run)

    job = orch.get_job(job_id)
    return JobResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        message="Job queued",
        created_at=job["created_at"],
        updated_at=job["updated_at"],
    )


@router.post("/run/sync", response_model=JobResponse)
async def run_agent_sync(request: AgentRunRequest):
    """
    Chạy agent đồng bộ (chờ kết quả).
    Body: { "query": "...", "ticker": "VNM" }  — ticker optional.
    """
    orch = get_orchestrator()
    job = orch.run(request.query, ticker=request.ticker)
    return JobResponse(
        job_id=job["job_id"],
        status=job["status"],
        message=job["message"],
        created_at=job["created_at"],
        updated_at=job["updated_at"],
        result=job.get("result"),
        error=job.get("error"),
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
        result=job.get("result"),
        error=job.get("error"),
    )
