"""Shared API schemas and the unified error envelope."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    """One consistent error shape for every API failure."""

    code: str = Field(..., description="Machine-readable error code, e.g. 'pair_not_found'.")
    message: str = Field(..., description="Clear, human-readable explanation.")
    details: Any | None = Field(
        None, description="Optional structured details (e.g. validation errors)."
    )


class ErrorEnvelope(BaseModel):
    """Wrapper returned by every error response."""

    error: ErrorBody


class HealthResponse(BaseModel):
    status: str = Field(..., description="'ok' when the service is operational.")
    app_name: str
    version: str
    data_mode: str = Field(..., description="Configured DATA_MODE: demo | auto | live.")
    database: str = Field(..., description="'connected' or 'error'.")
    pair_count: int
    price_bar_count: int
    latest_data_timestamp: str | None = Field(
        None, description="ISO timestamp of the newest stored bar."
    )
    latest_data_source: str | None = Field(
        None, description="Data source of the newest stored bar."
    )
    disclaimer: str


class MessageResponse(BaseModel):
    message: str
    details: dict | None = None
