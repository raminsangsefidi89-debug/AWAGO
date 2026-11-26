"""Structured logging with size-based rotation and per-request/job correlation ids."""

from __future__ import annotations

import contextvars
import logging
import logging.handlers
import sys
import uuid
from pathlib import Path

_FORMAT = "%(asctime)s | %(levelname)-8s | %(cid)s | %(name)s | %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"

_configured = False

correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default="-"
)


class CorrelationIdFilter(logging.Filter):
    """Injects the current correlation id into every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.cid = correlation_id_var.get()
        return True


def new_correlation_id() -> str:
    return uuid.uuid4().hex[:12]


def set_correlation_id(cid: str | None = None) -> str:
    value = cid or new_correlation_id()
    correlation_id_var.set(value)
    return value


def get_correlation_id() -> str:
    return correlation_id_var.get()


def setup_logging(log_dir: str | Path, level: str = "INFO") -> None:
    """Configure root logger: rotating file handler + console handler.

    The file handler writes ``awago.log`` (rotated at 2 MB, 5 backups)
    inside ``log_dir``. Safe to call more than once.
    """
    global _configured
    if _configured:
        return

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)
    corr_filter = CorrelationIdFilter()

    file_handler = logging.handlers.RotatingFileHandler(
        log_path / "awago.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(corr_filter)
    root.addHandler(file_handler)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    console.addFilter(corr_filter)
    root.addHandler(console)

    # Quiet noisy third-party loggers.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger."""
    return logging.getLogger(name)
