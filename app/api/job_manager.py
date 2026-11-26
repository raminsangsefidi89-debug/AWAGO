"""In-process background job manager: persistent queue, cancellation, guards."""

from __future__ import annotations

import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.config import get_settings
from app.db.engine import session_scope
from app.db.models import JobRecord
from app.logging_config import get_correlation_id, get_logger, set_correlation_id

logger = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class JobCancelled(RuntimeError):
    """Raised inside a job when cancellation was requested."""


def check_resources(min_disk_mb: int = 200, min_ram_mb: int = 256) -> str | None:
    """Return a human-readable refusal reason, or None when resources suffice."""
    import shutil

    try:
        free_disk_mb = shutil.disk_usage(".").free // (1024 * 1024)
        if free_disk_mb < min_disk_mb:
            return f"Not enough free disk: {free_disk_mb} MB available, {min_disk_mb} MB required."
    except OSError:
        pass
    try:
        import os

        page = os.sysconf("SC_PAGE_SIZE")
        available = os.sysconf("SC_AVPHYS_PAGES")
        free_ram_mb = page * available // (1024 * 1024)
        if free_ram_mb < min_ram_mb:
            return f"Not enough free memory: {free_ram_mb} MB available, {min_ram_mb} MB required."
    except (ValueError, OSError, AttributeError):
        pass  # platform without sysconf — skip the RAM check
    return None


class JobManager:
    """Runs collect/train jobs on worker threads with DB status tracking.

    Jobs are persistent (``job_records``), cancelable cooperatively via
    :meth:`request_cancel`, and limited to a small worker pool suited to a
    laptop.
    """

    def __init__(self, max_workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="awago-job")
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    def submit(self, job_type: str, params: dict[str, Any] | None = None) -> JobRecord:
        params = params or {}
        job_id = str(uuid.uuid4())
        with session_scope() as session:
            job = JobRecord(
                id=job_id,
                type=job_type,
                status="queued",
                params_json=json.dumps(params),
                progress=0.0,
                message="Queued",
                correlation_id=get_correlation_id(),
            )
            session.add(job)
            session.commit()
            session.refresh(job)
            record = job
        self._executor.submit(self._run, job_id, job_type, params)
        return record

    def get(self, job_id: str) -> JobRecord | None:
        with session_scope() as session:
            return session.get(JobRecord, job_id)

    def list_jobs(self, limit: int = 50) -> list[JobRecord]:
        with session_scope() as session:
            return list(
                session.scalars(
                    select(JobRecord).order_by(JobRecord.created_at.desc()).limit(limit)
                ).all()
            )

    def request_cancel(self, job_id: str) -> bool:
        """Flag a job for cooperative cancellation. Returns False if unknown."""
        with session_scope() as session:
            job = session.get(JobRecord, job_id)
            if job is None:
                return False
            if job.status in ("done", "failed", "cancelled"):
                return True
            job.cancel_requested = True
            job.message = "Cancellation requested"
            session.commit()
            return True

    def _cancel_requested(self, job_id: str) -> bool:
        with session_scope() as session:
            job = session.get(JobRecord, job_id)
            return bool(job and job.cancel_requested)

    def _check_cancel(self, job_id: str) -> None:
        if self._cancel_requested(job_id):
            raise JobCancelled(f"Job {job_id} cancelled")

    # ------------------------------------------------------------------
    def _update(self, job_id: str, **fields: Any) -> None:
        with session_scope() as session:
            job = session.get(JobRecord, job_id)
            if job is None:
                return
            for key, value in fields.items():
                setattr(job, key, value)
            session.commit()

    def _run(self, job_id: str, job_type: str, params: dict[str, Any]) -> None:
        record = self.get(job_id)
        set_correlation_id((record.correlation_id or None) if record is not None else None)
        self._update(job_id, status="running", started_at=_now(), message="Started")
        try:
            if job_type == "collect-data":
                result = self._run_collect(params, job_id)
            elif job_type == "train":
                result = self._run_train(params, job_id)
            elif job_type == "experiment":
                result = self._run_experiment(params, job_id)
            else:
                raise ValueError(f"Unknown job type: {job_type}")
            self._update(
                job_id,
                status="done",
                progress=1.0,
                message="Completed",
                result_json=json.dumps(result),
                finished_at=_now(),
            )
        except JobCancelled as exc:
            logger.info("Job %s cancelled", job_id)
            self._update(job_id, status="cancelled", message=str(exc)[:500], finished_at=_now())
        except Exception as exc:
            logger.exception("Job %s (%s) failed", job_id, job_type)
            self._update(job_id, status="failed", message=str(exc)[:500], finished_at=_now())

    def _run_collect(self, params: dict[str, Any], job_id: str) -> dict[str, Any]:
        from app.services.market import collect_data, ensure_pairs

        settings = get_settings()
        self._check_cancel(job_id)
        with session_scope() as session:
            ensure_pairs(session, settings)
            summary = collect_data(session, settings, pairs=params.get("pairs"))
        self._check_cancel(job_id)
        self._update(job_id, progress=0.9, message="Collection finished")
        return summary

    def _run_experiment(self, params: dict[str, Any], job_id: str) -> dict[str, Any]:
        from app.services.evaluation.runner import run_experiment

        settings = get_settings()

        def progress(frac: float, msg: str) -> None:
            self._update(job_id, progress=round(frac, 3), message=msg[:500])

        self._check_cancel(job_id)
        with session_scope() as session:
            board = run_experiment(
                session,
                pairs=params.get("pairs"),
                horizons=params.get("horizons"),
                model_names=params.get("models"),
                settings=settings,
                quick=bool(params.get("quick", True)),
                scheme=params.get("scheme", "expanding"),
                n_splits=params.get("n_splits"),
                progress_cb=progress,
            )
        self._check_cancel(job_id)
        return {
            "run_id": board["run_id"],
            "n_rows": board["n_rows"],
            "elapsed_seconds": board["elapsed_seconds"],
        }

    def _run_train(self, params: dict[str, Any], job_id: str) -> dict[str, Any]:
        from app.services.forecasting.training import train_pair
        from app.services.market import validate_pair_symbol

        refusal = check_resources()
        if refusal:
            raise RuntimeError(f"Refusing to start training: {refusal}")

        settings = get_settings()
        pairs = (
            [validate_pair_symbol(p) for p in params["pairs"]]
            if params.get("pairs")
            else list(settings.pairs_list)
        )
        horizons = (
            sorted({int(h) for h in params["horizons"]})
            if params.get("horizons")
            else settings.horizons_list
        )
        quick = bool(params.get("quick", False))

        results: dict[str, Any] = {}
        n = max(1, len(pairs))
        for i, pair in enumerate(pairs):
            self._check_cancel(job_id)

            def progress_cb(frac: float, msg: str, _i: int = i, _pair: str = pair) -> None:
                self._update(
                    job_id,
                    progress=round((_i + frac) / n, 3),
                    message=f"{_pair}: {msg}",
                )

            with session_scope() as session:
                results[pair] = train_pair(
                    session,
                    pair,
                    horizons=horizons,
                    settings=settings,
                    quick=quick,
                    progress=progress_cb,
                )
        return results


# Singleton used by the API layer.
job_manager = JobManager()
