"""Async job endpoints: data collection and model training.

Access control: localhost only, or any host with a valid X-API-Token
(the token is configured as API_TOKEN in .env).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request

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
    body: Optional[JobRequest] = None,
    settings: Settings = Depends(get_settings),
) -> JobStatus:
    """Fetch and store price history for the configured pairs (background job)."""
    require_job_access(request)
    params = {"pairs": (body.pairs if body else None)}
    if params["pairs"]:
        from app.services.market import validate_pair_symbol

        try:
            params["pairs"] = [validate_pair_symbol(p) for p in params["pairs"]]
        except ValueError as exc:
            raise BadRequestError(str(exc), code="invalid_pair_format") from exc
    job = job_manager.submit("collect-data", params)
    return _job_status(job)


@router.post(
    "/jobs/train",
    response_model=JobStatus,
    summary="Start a model-training job",
)
def start_train_job(request: Request, body: Optional[JobRequest] = None) -> JobStatus:
    """Train forecasting models for the configured pairs/horizons (background job)."""
    require_job_access(request)
    params = {
        "pairs": (body.pairs if body else None),
        "horizons": (body.horizons if body else None),
        "quick": bool(body.quick) if body else False,
    }
    if params["pairs"]:
        from app.services.market import validate_pair_symbol

        try:
            params["pairs"] = [validate_pair_symbol(p) for p in params["pairs"]]
        except ValueError as exc:
            raise BadRequestError(str(exc), code="invalid_pair_format") from exc
    if params["horizons"]:
        params["horizons"] = [int(h) for h in params["horizons"]]
        if any(h <= 0 or h > 365 for h in params["horizons"]):
            raise BadRequestError("Horizons must be integers in 1..365", code="invalid_horizon")
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
