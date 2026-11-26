"""In-process background job manager for data collection and training."""

from __future__ import annotations

import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from app.config import get_settings
from app.db.engine import session_scope
from app.db.models import JobRecord
from app.logging_config import get_logger

logger = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class JobManager:
    """Runs collect/train jobs on worker threads with DB status tracking."""

    def __init__(self, max_workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="awago-job")
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    def submit(self, job_type: str, params: Optional[Dict[str, Any]] = None) -> JobRecord:
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
            )
            session.add(job)
            session.commit()
            session.refresh(job)
            record = job
        self._executor.submit(self._run, job_id, job_type, params)
        return record

    def get(self, job_id: str) -> Optional[JobRecord]:
        with session_scope() as session:
            return session.get(JobRecord, job_id)

    def list_jobs(self, limit: int = 50) -> List[JobRecord]:
        with session_scope() as session:
            return list(
                session.scalars(
                    select(JobRecord).order_by(JobRecord.created_at.desc()).limit(limit)
                ).all()
            )

    # ------------------------------------------------------------------
    def _update(self, job_id: str, **fields: Any) -> None:
        with session_scope() as session:
            job = session.get(JobRecord, job_id)
            if job is None:
                return
            for key, value in fields.items():
                setattr(job, key, value)
            session.commit()

    def _run(self, job_id: str, job_type: str, params: Dict[str, Any]) -> None:
        self._update(job_id, status="running", started_at=_now(), message="Started")
        try:
            if job_type == "collect-data":
                result = self._run_collect(params, job_id)
            elif job_type == "train":
                result = self._run_train(params, job_id)
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
        except Exception as exc:  # noqa: BLE001 — job failures are recorded, not raised
            logger.exception("Job %s (%s) failed", job_id, job_type)
            self._update(
                job_id,
                status="failed",
                message=str(exc)[:500],
                finished_at=_now(),
            )

    def _run_collect(self, params: Dict[str, Any], job_id: str) -> Dict[str, Any]:
        from app.services.market import collect_data, ensure_pairs

        settings = get_settings()
        with session_scope() as session:
            ensure_pairs(session, settings)
            summary = collect_data(
                session,
                settings,
                pairs=params.get("pairs"),
            )
        self._update(job_id, progress=0.9, message="Collection finished")
        return summary

    def _run_train(self, params: Dict[str, Any], job_id: str) -> Dict[str, Any]:
        from app.services.forecasting.training import train_pair
        from app.services.market import validate_pair_symbol

        settings = get_settings()
        pairs = [validate_pair_symbol(p) for p in params["pairs"]] if params.get("pairs") else list(settings.pairs_list)
        horizons = sorted(set(int(h) for h in params["horizons"])) if params.get("horizons") else settings.horizons_list
        quick = bool(params.get("quick", False))

        results: Dict[str, Any] = {}
        n = max(1, len(pairs))
        for i, pair in enumerate(pairs):
            def progress_cb(frac: float, msg: str, _i: int = i) -> None:
                self._update(
                    job_id,
                    progress=round((_i + frac) / n, 3),
                    message=f"{pair}: {msg}",
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
