from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.agent.orchestrator import AgentOrchestrator
from app.models.schemas import AgentRunRequest, JobResponse, JobStatus

router = APIRouter(prefix="/agent", tags=["Agent"])

# Singleton orchestrator (in-memory jobs for simplicity; use Redis for multi-worker)
_orchestrator: Optional[AgentOrchestrator] = None


def get_orchestrator() -> AgentOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator()
    return _orchestrator


@router.post("/run", response_model=JobResponse)
async def run_agent(request: AgentRunRequest, background_tasks: BackgroundTasks):
    """
    Chạy agent với câu hỏi tự nhiên.
    Job chạy nền, trả về job_id ngay. Dùng GET /agent/jobs/{job_id} để theo dõi.
    """
    orch = get_orchestrator()
    job_id = orch.create_job(request.query)

    def _run():
        orch.run(request.query, job_id=job_id)

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
    Chạy agent đồng bộ (chờ kết quả). Dùng cho test hoặc job ngắn.
    """
    orch = get_orchestrator()
    job = orch.run(request.query)
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
