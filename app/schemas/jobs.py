"""Job schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class JobRequest(BaseModel):
    pairs: list[str] | None = Field(
        None, description="Optional subset of pairs (default: all configured pairs)."
    )
    horizons: list[int] | None = Field(
        None, description="Optional subset of horizons in days (default: configured horizons)."
    )
    quick: bool = Field(False, description="Use a reduced configuration for a faster run.")


class JobStatus(BaseModel):
    id: str
    type: str = Field(..., description="'collect-data' or 'train'.")
    status: str = Field(..., description="'queued' | 'running' | 'done' | 'failed'.")
    progress: float = Field(..., description="0..1 completion estimate.")
    message: str = ""
    params: dict[str, Any] = {}
    result: dict[str, Any] = {}
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class JobListResponse(BaseModel):
    jobs: list[JobStatus]
    count: int
