"""Series export endpoints (CSV / Parquet)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.params import normalize_pair, pair_or_404
from app.db.engine import get_db
from app.services.market import get_history

router = APIRouter(tags=["export"])


@router.get("/pairs/{pair}/export", summary="Export history as CSV or Parquet (slug)")
def export_series(
    pair: str,
    format: str = Query("csv", pattern="^(csv|parquet)$", description="Export format."),
    db: Session = Depends(get_db),
) -> Response:
    """Download the pair's stored history with full provenance columns."""
    symbol = normalize_pair(pair)
    pair_or_404(db, symbol)
    return _export(symbol, format, db)


@router.get(
    "/pairs/{base}/{quote}/export",
    summary="Export history (BASE/QUOTE)",
    include_in_schema=False,
)
def export_series_split(
    base: str,
    quote: str,
    format: str = Query("csv", pattern="^(csv|parquet)$"),
    db: Session = Depends(get_db),
) -> Response:
    symbol = normalize_pair(f"{base}/{quote}")
    pair_or_404(db, symbol)
    return _export(symbol, format, db)


def _export(symbol: str, format: str, db: Session) -> Response:
    import io

    import pandas as pd

    bars = get_history(db, symbol)
    df = pd.DataFrame(
        {
            "timestamp": [b.timestamp.isoformat() for b in bars],
            "open": [b.open for b in bars],
            "high": [b.high for b in bars],
            "low": [b.low for b in bars],
            "close": [b.close for b in bars],
            "volume": [b.volume for b in bars],
            "data_source": [b.data_source for b in bars],
            "is_demo": [b.is_demo for b in bars],
            "dataset_version": [b.dataset_version for b in bars],
            "quality_flag": [b.quality_flag for b in bars],
        }
    )
    slug = symbol.replace("/", "")
    if format == "csv":
        buf = io.StringIO()
        df.to_csv(buf, index=False)
        return Response(
            content=buf.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{slug}.csv"'},
        )
    raw = io.BytesIO()
    df.to_parquet(raw, engine="pyarrow", compression="zstd", index=False)
    return Response(
        content=raw.getvalue(),
        media_type="application/vnd.apache.parquet",
        headers={"Content-Disposition": f'attachment; filename="{slug}.parquet"'},
    )
