"""Shared bootstrap helpers for the CLI scripts."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def bootstrap() -> None:
    """Make the repository root importable when scripts run as plain files."""
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
