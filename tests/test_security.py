"""Job-endpoint access control and secret hygiene."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api.deps import require_job_access
from app.api.errors import ForbiddenError


def _request(host: str, token: str = ""):
    return SimpleNamespace(
        client=SimpleNamespace(host=host),
        headers={"x-api-token": token} if token else {},
    )


def test_localhost_allowed_without_token():
    require_job_access(_request("127.0.0.1"))
    require_job_access(_request("::1"))
    require_job_access(_request("127.0.0.53"))


def test_remote_denied_without_token():
    with pytest.raises(ForbiddenError):
        require_job_access(_request("203.0.113.7"))


def test_remote_denied_with_wrong_token(monkeypatch):
    from app.config import get_settings

    get_settings.cache_clear()
    import os

    os.environ["API_TOKEN"] = "secret-token-abc"
    try:
        get_settings.cache_clear()
        with pytest.raises(ForbiddenError):
            require_job_access(_request("203.0.113.7", token="wrong"))
    finally:
        os.environ.pop("API_TOKEN", None)
        get_settings.cache_clear()


def test_remote_allowed_with_valid_token():
    import os

    from app.config import get_settings

    os.environ["API_TOKEN"] = "secret-token-abc"
    try:
        get_settings.cache_clear()
        require_job_access(_request("203.0.113.7", token="secret-token-abc"))
    finally:
        os.environ.pop("API_TOKEN", None)
        get_settings.cache_clear()


def test_no_secret_in_repo_files():
    """The example env file must not contain a real token."""
    from pathlib import Path

    repo = Path(__file__).resolve().parent.parent
    env_example = (repo / ".env.example").read_text(encoding="utf-8")
    assert "API_TOKEN=change-me" in env_example
    # .env must be gitignored
    gitignore = (repo / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gitignore
