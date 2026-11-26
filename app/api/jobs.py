"""Async job endpoints: data collection and model training.

Access control: localhost only, or any host with a valid X-API-Token
(the token is configured as API_TOKEN in .env).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.deps import require_job_access
from app.api.errors import BadRequestError, NotFoundError
from app.api.job_manager import job_manager
from app.config import Settings, get_settings
from app.schemas.jobs import JobListResponse, JobRequest, JobStatus

router = APIRouter(tags=["jobs"])


def _job_status(job) -> JobStatus:
    import json

    try:
        params = json.loads(job.params_json or "{}")
    except ValueError:
        params = {}
    try:
        result = json.loads(job.result_json or "{}")
    except ValueError:
        result = {}
    return JobStatus(
        id=job.id,
        type=job.type,
        status=job.status,
        progress=job.progress,
        message=job.message,
        params=params,
        result=result,
        created_at=job.created_at.isoformat() if job.created_at else None,
        started_at=job.started_at.isoformat() if job.started_at else None,
        finished_at=job.finished_at.isoformat() if job.finished_at else None,
    )


@router.post(
    "/jobs/collect-data",
    response_model=JobStatus,
    summary="Start a data-collection job",
)
def start_collect_job(
    request: Request,
    body: JobRequest | None = None,
    settings: Settings = Depends(get_settings),
) -> JobStatus:
    """Fetch and store price history for the configured pairs (background job)."""
    _ = settings
    require_job_access(request)
    pairs: list[str] | None = None
    if body and body.pairs:
        from app.services.market import validate_pair_symbol

        try:
            pairs = [validate_pair_symbol(p) for p in body.pairs]
        except ValueError as exc:
            raise BadRequestError(str(exc), code="invalid_pair_format") from exc
    job = job_manager.submit("collect-data", {"pairs": pairs})
    return _job_status(job)


@router.post(
    "/jobs/train",
    response_model=JobStatus,
    summary="Start a model-training job",
)
def start_train_job(request: Request, body: JobRequest | None = None) -> JobStatus:
    """Train forecasting models for the configured pairs/horizons (background job)."""
    require_job_access(request)
    pairs: list[str] | None = None
    if body and body.pairs:
        from app.services.market import validate_pair_symbol

        try:
            pairs = [validate_pair_symbol(p) for p in body.pairs]
        except ValueError as exc:
            raise BadRequestError(str(exc), code="invalid_pair_format") from exc
    horizons: list[int] | None = None
    if body and body.horizons:
        horizons = [int(h) for h in body.horizons]
        if any(h <= 0 or h > 365 for h in horizons):
            raise BadRequestError("Horizons must be integers in 1..365", code="invalid_horizon")
    params: dict = {
        "pairs": pairs,
        "horizons": horizons,
        "quick": bool(body.quick) if body else False,
    }
    job = job_manager.submit("train", params)
    return _job_status(job)


@router.get("/jobs", response_model=JobListResponse, summary="List recent jobs")
def list_jobs(request: Request) -> JobListResponse:
    require_job_access(request)
    jobs = [_job_status(j) for j in job_manager.list_jobs()]
    return JobListResponse(jobs=jobs, count=len(jobs))


@router.get("/jobs/{job_id}", response_model=JobStatus, summary="Job status")
def get_job(request: Request, job_id: str) -> JobStatus:
    """Query the status, progress and result of a previously submitted job."""
    require_job_access(request)
    job = job_manager.get(job_id)
    if job is None:
        raise NotFoundError(f"Job not found: {job_id}", code="job_not_found")
    return _job_status(job)


@router.get("/jobs/{job_id}/events", summary="SSE stream of job progress")
def stream_job(request: Request, job_id: str):
    """Server-sent events: {status, progress, message} every ~0.7s until done."""
    import asyncio
    import json as _json

    require_job_access(request)
    if job_manager.get(job_id) is None:
        raise NotFoundError(f"Job not found: {job_id}", code="job_not_found")

    async def _gen():
        while True:
            job = job_manager.get(job_id)
            if job is None:
                break
            payload = _json.dumps(
                {"status": job.status, "progress": job.progress, "message": job.message}
            )
            yield f"data: {payload}\n\n"
            if job.status in ("done", "failed", "cancelled"):
                break
            await asyncio.sleep(0.7)

    return StreamingResponse(_gen(), media_type="text/event-stream")


@router.post("/jobs/{job_id}/cancel", response_model=JobStatus, summary="Request job cancellation")
def cancel_job(request: Request, job_id: str) -> JobStatus:
    """Cooperatively cancel a queued or running job."""
    require_job_access(request)
    if not job_manager.request_cancel(job_id):
        raise NotFoundError(f"Job not found: {job_id}", code="job_not_found")
    job = job_manager.get(job_id)
    assert job is not None
    return _job_status(job)
