"""Columnar series store: Parquet mirrors under data/series/ (pyarrow).

SQLite stays the source of truth for bars (v1 compatibility). Every ingest
writes/refreshes a Parquet mirror per (pair, data_source) so bulk queries,
exports and quality checks are fast. Queries use DuckDB when installed
(optional), otherwise pandas.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from app.config import DATA_DIR, Settings, get_settings
from app.logging_config import get_logger

logger = get_logger(__name__)

try:
    import duckdb

    HAS_DUCKDB = True
except Exception:
    duckdb = None  # type: ignore[assignment]
    HAS_DUCKDB = False

_SLUG_RE = re.compile(r"[^A-Za-z0-9_-]")


def _slug(value: str) -> str:
    return _SLUG_RE.sub("_", value.strip().upper())


def series_path(pair_symbol: str, data_source: str, series_dir: Path | None = None) -> Path:
    d = series_dir or (DATA_DIR / "series")
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{_slug(pair_symbol)}__{_slug(data_source)}.parquet"


def write_series(
    df: pd.DataFrame, pair_symbol: str, data_source: str, series_dir: Path | None = None
) -> Path:
    """Persist a bar frame (timestamp, open, high, low, close, ...) to Parquet."""
    path = series_path(pair_symbol, data_source, series_dir)
    out = df.copy()
    if "timestamp" in out.columns:
        out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    out.to_parquet(path, engine="pyarrow", compression="zstd", index=False)
    logger.debug("Wrote series mirror %s (%d rows)", path, len(out))
    return path


def read_series(
    pair_symbol: str,
    data_source: str,
    start: str | None = None,
    end: str | None = None,
    series_dir: Path | None = None,
) -> pd.DataFrame:
    """Read a bar frame from Parquet (DuckDB when available, else pandas)."""
    path = series_path(pair_symbol, data_source, series_dir)
    if not path.exists():
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close"])
    if HAS_DUCKDB:
        return _read_with_duckdb(path, start, end)
    return _read_with_pandas(path, start, end)


def _read_with_pandas(path: Path, start: str | None, end: str | None) -> pd.DataFrame:
    df = pd.read_parquet(path, engine="pyarrow")
    if start:
        df = df[df["timestamp"] >= pd.to_datetime(start, utc=True)]
    if end:
        df = df[df["timestamp"] <= pd.to_datetime(end, utc=True)]
    return df.sort_values("timestamp").reset_index(drop=True)


def _read_with_duckdb(path: Path, start: str | None, end: str | None) -> pd.DataFrame:
    # Path comes from ``series_path`` (safe slug chars only); DuckDB cannot
    # bind parameters inside table-function names, so quote it inline.
    escaped = str(path).replace("'", "''")
    con = duckdb.connect(database=":memory:")
    try:
        where, params = [], []
        if start:
            where.append("timestamp >= ?")
            params.append(start)
        if end:
            where.append("timestamp <= ?")
            params.append(end)
        sql = f"SELECT * FROM read_parquet('{escaped}')"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY timestamp"
        return con.execute(sql, params).df()
    finally:
        con.close()


def delete_series(pair_symbol: str, data_source: str, series_dir: Path | None = None) -> bool:
    path = series_path(pair_symbol, data_source, series_dir)
    if path.exists():
        path.unlink()
        return True
    return False


def snapshot_hash_for(pair_symbol: str, data_source: str, settings: Settings | None = None) -> str:
    """Reproducibility hash of one stored series."""
    from app.repro import snapshot_hash

    df = read_series(pair_symbol, data_source, series_dir=(settings or get_settings()).series_dir)
    rows = [(str(r.timestamp), float(r.close)) for r in df.itertuples()]
    return snapshot_hash(rows)
