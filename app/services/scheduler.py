"""Minimal thread-based local scheduler (disabled by default; never blocks startup).

Purpose: periodic data refresh (and optional retraining) on a laptop. No
external dependencies — a daemon thread with a fixed interval. Only started
when ``SCHEDULER_ENABLED=true``.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from app.logging_config import get_logger

logger = get_logger(__name__)


class LocalScheduler:
    """Runs ``job`` every ``interval_minutes`` on a daemon thread."""

    def __init__(
        self, interval_minutes: int, job: Callable[[], None], name: str = "awago-scheduler"
    ) -> None:
        self.interval_seconds = max(30, interval_minutes * 60)
        self.job = job
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)

    def start(self) -> None:
        logger.info("Scheduler started (interval=%ds)", self.interval_seconds)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                logger.info("Scheduler tick: running job")
                self.job()
            except Exception:
                logger.exception("Scheduler job failed")


_scheduler: LocalScheduler | None = None


def start_scheduler_if_enabled(settings) -> LocalScheduler | None:
    """Start the scheduler when configured. Returns the instance (or None)."""
    global _scheduler
    if not getattr(settings, "scheduler_enabled", False):
        return None
    if _scheduler is not None:
        return _scheduler

    def _tick() -> None:
        from app.api.job_manager import job_manager

        job_manager.submit("collect-data", {})
        if getattr(settings, "scheduler_retrain", False):
            job_manager.submit("train", {"quick": True})

    _scheduler = LocalScheduler(
        interval_minutes=getattr(settings, "scheduler_interval_minutes", 60),
        job=_tick,
    )
    _scheduler.start()
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.stop()
        _scheduler = None
