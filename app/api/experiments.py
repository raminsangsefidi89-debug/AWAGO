"""Experiment runs, leaderboards, and the model registry API."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query, Request

from app.api.deps import require_job_access
from app.api.errors import NotFoundError
from app.logging_config import get_logger

router = APIRouter(tags=["experiments"])
logger = get_logger(__name__)


def _leaderboard_path(run_id: str) -> Path:
    from app.config import DATA_DIR

    return DATA_DIR / "leaderboards" / f"{run_id}.json"


@router.post("/experiments/run", summary="Run a walk-forward experiment (background job)")
def start_experiment(request: Request, params: dict | None = None) -> dict:
    """Queue an experiment over the plugin model registry.

    Body (all optional): pairs, horizons, models, quick (default true),
    scheme ('expanding'|'rolling'), n_splits.
    """
    require_job_access(request)
    from app.api.job_manager import job_manager

    job = job_manager.submit("experiment", params or {})
    return {"job_id": job.id, "status": job.status, "poll": f"/api/v1/jobs/{job.id}"}


@router.get("/experiments/runs", summary="List experiment runs")
def list_runs(limit: int = Query(20, ge=1, le=100)) -> dict:
    """All persisted leaderboards (newest first) with their run_ids."""
    from app.config import DATA_DIR

    out = []
    board_dir = DATA_DIR / "leaderboards"
    if board_dir.exists():
        files = sorted(board_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in files[:limit]:
            if path.name == "latest.json":
                continue
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
                out.append(
                    {
                        "run_id": doc.get("run_id"),
                        "generated_at": doc.get("generated_at"),
                        "n_rows": doc.get("n_rows"),
                        "elapsed_seconds": doc.get("elapsed_seconds"),
                        "pairs": doc.get("pairs"),
                        "horizons": doc.get("horizons"),
                    }
                )
            except ValueError:
                continue
    return {"runs": out}


@router.get("/experiments/runs/{run_id}", summary="Leaderboard for one run")
def get_run(run_id: str) -> dict:
    path = _leaderboard_path(run_id)
    if not path.exists():
        raise NotFoundError(f"Run not found: {run_id}", code="run_not_found")
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/leaderboards/latest", summary="Latest leaderboard")
def latest_leaderboard() -> dict:
    from app.config import DATA_DIR

    path = DATA_DIR / "leaderboards" / "latest.json"
    if not path.exists():
        raise NotFoundError("No leaderboard yet — run an experiment first.", code="no_leaderboard")
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/leaderboards/{run_id}", summary="Leaderboard by run id")
def leaderboard_by_id(run_id: str) -> dict:
    return get_run(run_id)


@router.get("/reports/{run_id}", summary="Persian RTL print report (computed outputs only)")
def get_report(run_id: str = "latest") -> Any:
    """Self-contained print-friendly HTML report generated strictly from the
    stored leaderboard/quality artifacts of this run — no recomputed numbers."""
    from fastapi.responses import HTMLResponse

    from app.services.report.generator import generate_report

    try:
        html = generate_report(run_id)
    except FileNotFoundError as exc:
        raise NotFoundError(str(exc), code="run_not_found") from exc
    return HTMLResponse(content=html)


# ----------------------------------------------------------------------
# Model registry
# ----------------------------------------------------------------------


@router.get("/registry/models", summary="Registered models + availability")
def registry_models() -> dict:
    from app.models_availability import models_catalog

    return models_catalog()


@router.get("/registry/artifacts", summary="Saved artifacts + champions + audit trail")
def registry_artifacts(name: str | None = None) -> dict:
    from app.services.models.lifecycle import list_artifacts, registry_dir

    champions_path = registry_dir() / "champions.json"
    champions = (
        json.loads(champions_path.read_text(encoding="utf-8")) if champions_path.exists() else {}
    )
    events = []
    events_path = registry_dir() / "events.jsonl"
    if events_path.exists():
        for line in events_path.read_text(encoding="utf-8").splitlines()[-50:]:
            try:
                events.append(json.loads(line))
            except ValueError:
                continue
    return {"artifacts": list_artifacts(name), "champions": champions, "recent_events": events}


@router.post("/registry/compare", summary="Paired-bootstrap comparison of two models")
def registry_compare(payload: dict) -> dict:
    """Body: {"errors_a": [...], "errors_b": [...], "n_boot": 1000} — absolute
    error series of challenger (a) and champion (b) on the same rows."""
    import numpy as np

    from app.services.models.lifecycle import bootstrap_significance

    result = bootstrap_significance(
        np.asarray(payload.get("errors_a", []), dtype=float),
        np.asarray(payload.get("errors_b", []), dtype=float),
        n_boot=int(payload.get("n_boot", 1000)),
    )
    result["note"] = (
        "Verdict compares |error| means; 'a_better' means the challenger has significantly smaller errors."
    )
    return result


@router.post("/registry/promote", summary="Promote a model to champion (audited)")
def registry_promote(request: Request, payload: dict) -> dict:
    """Body: {"pair": "EUR/USD", "horizon": 7, "model": "ml_ridge"}. Manual
    promotion is recorded in the audit trail with reason 'manual'."""
    require_job_access(request)
    from app.services.models.lifecycle import log_event, set_champion

    pair = str(payload.get("pair", ""))
    horizon = int(payload.get("horizon", 1))
    model = str(payload.get("model", ""))
    if not pair or not model:
        raise NotFoundError("pair and model are required", code="bad_payload")
    set_champion(pair, horizon, model)
    log_event("promote", {"pair": pair, "horizon": horizon, "champion": model, "reason": "manual"})
    return {"pair": pair, "horizon": horizon, "champion": model, "reason": "manual"}


@router.post("/registry/rollback", summary="Roll back the champion (audited)")
def registry_rollback(request: Request, payload: dict) -> dict:
    """Body: {"pair": "EUR/USD", "horizon": 7, "to": "baseline_naive"}."""
    require_job_access(request)
    from app.services.models.lifecycle import log_event, set_champion

    pair = str(payload.get("pair", ""))
    horizon = int(payload.get("horizon", 1))
    to = str(payload.get("to", ""))
    if not pair or not to:
        raise NotFoundError("pair and to are required", code="bad_payload")
    set_champion(pair, horizon, to)
    log_event(
        "rollback", {"pair": pair, "horizon": horizon, "champion": to, "reason": "manual-rollback"}
    )
    return {"pair": pair, "horizon": horizon, "champion": to, "reason": "manual-rollback"}
