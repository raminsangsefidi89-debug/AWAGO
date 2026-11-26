"""Shared FastAPI dependencies (DB session, job-endpoint access control)."""

from __future__ import annotations

from fastapi import Request

from app.api.errors import ForbiddenError
from app.config import get_settings

LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def client_is_local(request: Request) -> bool:
    host = request.client.host if request.client else ""
    return host in LOOPBACK_HOSTS or host.startswith("127.") or host.startswith("::ffff:127.")


def require_job_access(request: Request) -> None:
    """Allow job endpoints from localhost, or remotely with a valid API token.

    Raises ForbiddenError otherwise. The token comes from the API_TOKEN
    environment variable / .env file and is never logged.
    """
    settings = get_settings()
    if client_is_local(request):
        return
    token = request.headers.get("x-api-token", "")
    if settings.api_token and token and token == settings.api_token:
        return
    raise ForbiddenError(
        "Job endpoints are restricted to localhost or require a valid X-API-Token header."
    )
