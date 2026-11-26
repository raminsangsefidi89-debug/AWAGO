"""Shared path-parameter helpers for pair symbols.

Pairs are naturally written ``EUR/USD`` — but a ``/`` inside a URL path
segment does not route in Starlette. The API therefore accepts BOTH forms:

* ``/api/v1/pairs/EUR/USD/price``  (natural BASE/QUOTE, two path segments)
* ``/api/v1/pairs/EURUSD/price``   (single-segment slug)

Both normalize to the canonical ``EUR/USD`` symbol.
"""

from __future__ import annotations

from app.api.errors import BadRequestError, PairNotFoundError
from app.services.market import validate_pair_symbol


def normalize_pair(value: str) -> str:
    """Normalize a path pair value (``EUR/USD``, ``EUR-USD``, ``EURUSD``) to ``EUR/USD``."""
    v = (value or "").strip().upper()
    for sep in ("-", "_"):
        if sep in v and "/" not in v:
            v = v.replace(sep, "/")
    if "/" not in v and len(v) == 6:
        v = v[:3] + "/" + v[3:]
    try:
        return validate_pair_symbol(v)
    except ValueError as exc:
        raise BadRequestError(str(exc), code="invalid_pair_format") from exc


def pair_or_404(db, symbol: str) -> None:
    """Raise PairNotFoundError unless the pair exists in the database."""
    from sqlalchemy import select

    from app.db.models import CurrencyPair

    known = db.scalar(select(CurrencyPair).where(CurrencyPair.symbol == symbol))
    if known is None:
        raise PairNotFoundError(f"Unknown currency pair: {symbol}")
