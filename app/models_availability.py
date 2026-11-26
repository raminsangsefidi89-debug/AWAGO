"""Model catalog (registry + availability) — tiny import shim for the API."""

from __future__ import annotations

from typing import Any


def models_catalog() -> dict[str, Any]:
    from app.services.models.registry import available_models

    return {
        "models": available_models(),
        "note": (
            "Every model is evaluated by the same walk-forward harness; "
            "unavailable models list the exact missing dependency."
        ),
    }
