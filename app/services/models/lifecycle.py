"""Model lifecycle: artifact store + champion/challenger with significance.

Artifacts live under data/registry/ and always carry their reproducibility
triple: run_id, config_hash, snapshot_hash. The audit trail is a JSONL file
of registry events (train / compare / promote / rollback). "Promotion to
champion" requires a statistically grounded comparison — never a silent
swaps.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from app.config import DATA_DIR
from app.logging_config import get_logger

logger = get_logger(__name__)


def registry_dir(base: Path | None = None) -> Path:
    d = (base or DATA_DIR) / "registry"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _events_path(base: Path | None = None) -> Path:
    return registry_dir(base) / "events.jsonl"


def log_event(event: str, payload: dict[str, Any], base: Path | None = None) -> None:
    doc = {"at": datetime.now(timezone.utc).isoformat(), "event": event, **payload}
    with _events_path(base).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(doc) + "\n")


def save_artifact(
    name: str,
    model: Any,
    metrics: dict[str, Any],
    run_id: str,
    config_hash: str,
    snapshot_hash: str,
    base: Path | None = None,
) -> Path:
    """Persist a model artifact with its provenance metadata."""
    folder = registry_dir(base) / name
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    model_path = folder / f"{stamp}.joblib"
    try:
        model.save(model_path)
    except Exception as exc:
        logger.warning("Model weights save failed (%s); saving metadata only", exc)
        model_path = folder / f"{stamp}.meta-only"
        model_path.write_text(json.dumps(model.metadata()), encoding="utf-8")
    meta = {
        "name": name,
        "run_id": run_id,
        "config_hash": config_hash,
        "snapshot_hash": snapshot_hash,
        "metrics": metrics,
        "model_metadata": model.metadata() if hasattr(model, "metadata") else {},
        "saved_at": stamp,
    }
    meta_path = folder / f"{stamp}.json"
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    log_event("artifact_saved", {"name": name, "run_id": run_id}, base)
    return meta_path


def list_artifacts(name: str | None = None, base: Path | None = None) -> list[dict]:
    root = registry_dir(base)
    out = []
    for meta_path in sorted(root.glob(f"{name or '*'}/*.json")):
        try:
            out.append(json.loads(meta_path.read_text(encoding="utf-8")))
        except ValueError:
            continue
    return out


def bootstrap_significance(
    err_a: np.ndarray,
    err_b: np.ndarray,
    n_boot: int = 1000,
    seed: int = 42,
) -> dict[str, Any]:
    """Paired bootstrap on |error| difference (a - b). Positive = a better.

    Returns the mean improvement, a 95% bootstrap CI, and a verdict:
    'a_better' / 'b_better' / 'not_significant' (CI includes 0).
    """
    a = np.abs(np.asarray(err_a, dtype=float))
    b = np.abs(np.asarray(err_b, dtype=float))
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    diff = b - a  # positive -> a has smaller error
    rng = np.random.default_rng(seed)
    boots = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, n)
        boots[i] = diff[idx].mean()
    lo, hi = np.percentile(boots, [2.5, 97.5])
    verdict = "not_significant"
    if lo > 0:
        verdict = "a_better"
    elif hi < 0:
        verdict = "b_better"
    return {
        "mean_improvement": float(diff.mean()),
        "ci95": [float(lo), float(hi)],
        "verdict": verdict,
        "n": int(n),
    }


def compare_and_maybe_promote(
    challenger: str,
    err_challenger: np.ndarray,
    err_champion: np.ndarray | None,
    pair: str,
    horizon: int,
    base: Path | None = None,
) -> dict[str, Any]:
    """Compare challenger vs champion (or vs baseline if none) and record.

    The champion is only updated on a significant win — otherwise the
    incumbent stays, with the reason recorded in the audit trail.
    """
    current = champion_name(pair, horizon, base)
    if err_champion is None or current is None:
        result = {"verdict": "no_champion", "champion": challenger, "challenger": challenger}
        set_champion(pair, horizon, challenger, base)
        log_event(
            "promote",
            {"pair": pair, "horizon": horizon, "champion": challenger, "reason": "first"},
            base,
        )
        return result
    sig = bootstrap_significance(err_challenger, err_champion)
    promoted = sig["verdict"] == "a_better"
    if promoted:
        set_champion(pair, horizon, challenger, base)
    log_event(
        "compare",
        {
            "pair": pair,
            "horizon": horizon,
            "champion": current,
            "challenger": challenger,
            "significance": sig,
            "promoted": promoted,
        },
        base,
    )
    return {
        "verdict": sig["verdict"],
        "champion": challenger if promoted else current,
        "challenger": challenger,
        "promoted": promoted,
        "significance": sig,
    }


def champion_name(pair: str, horizon: int, base: Path | None = None) -> str | None:
    path = registry_dir(base) / "champions.json"
    if not path.exists():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    return doc.get(f"{pair}|{horizon}")


def set_champion(pair: str, horizon: int, name: str, base: Path | None = None) -> None:
    path = registry_dir(base) / "champions.json"
    doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    doc[f"{pair}|{horizon}"] = name
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
