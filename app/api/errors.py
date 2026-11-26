"""Centralized application errors and the unified error envelope."""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base class for API-facing errors with a consistent envelope shape."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code
        self.details = details

    def to_envelope(self) -> dict:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


class BadRequestError(AppError):
    status_code = 400
    code = "bad_request"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class PairNotFoundError(NotFoundError):
    code = "pair_not_found"


class ModelNotFoundErrorAPI(NotFoundError):
    code = "model_not_found"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "service_unavailable"


class DataUnavailableError(AppError):
    status_code = 503
    code = "data_unavailable"
