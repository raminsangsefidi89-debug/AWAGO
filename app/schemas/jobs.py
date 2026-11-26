"""Job schemas."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class JobRequest(BaseModel):
    pairs: Optional[List[str]] = Field(
        None, description="Optional subset of pairs (default: all configured pairs)."
    )
    horizons: Optional[List[int]] = Field(
        None, description="Optional subset of horizons in days (default: configured horizons)."
    )
    quick: bool = Field(False, description="Use a reduced configuration for a faster run.")


class JobStatus(BaseModel):
    id: str
    type: str = Field(..., description="'collect-data' or 'train'.")
    status: str = Field(..., description="'queued' | 'running' | 'done' | 'failed'.")
    progress: float = Field(..., description="0..1 completion estimate.")
    message: str = ""
    params: Dict[str, Any] = {}
    result: Dict[str, Any] = {}
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class JobListResponse(BaseModel):
    jobs: List[JobStatus]
    count: int
