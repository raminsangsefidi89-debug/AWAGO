"""Market-data service: pair management, collection with de-duplication, queries."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import CurrencyPair, PriceBar
from app.logging_config import get_logger
from app.services.data_providers import PriceBarData, get_provider

logger = get_logger(__name__)

# Persian display names for the default pairs (kept with the pair registry).
PAIR_NAMES_FA: dict[str, str] = {
    "EUR/USD": "یورو / دلار آمریکا",
    "GBP/USD": "پوند انگلیس / دلار آمریکا",
    "USD/JPY": "دلار آمریکا / ین ژاپن",
    "USD/CHF": "دلار آمریکا / فرانک سوئیس",
    "AUD/USD": "دلار استرالیا / دلار آمریکا",
    "USD/CAD": "دلار آمریکا / دلار کانادا",
    "NZD/USD": "دلار نیوزیلند / دلار آمریکا",
    "EUR/GBP": "یورو / پوند انگلیس",
    "EUR/JPY": "یورو / ین ژاپن",
    "USD/TRY": "دلار آمریکا / لیر ترکیه",
}


def validate_pair_symbol(symbol: str) -> str:
    """Validate and normalize a BASE/QUOTE symbol; raise ValueError if invalid."""
    symbol = (symbol or "").strip().upper()
    parts = symbol.split("/")
    if len(parts) != 2 or len(parts[0]) != 3 or len(parts[1]) != 3:
        raise ValueError(f"Invalid pair symbol {symbol!r}; expected BASE/QUOTE like EUR/USD")
    if not (parts[0].isalpha() and parts[1].isalpha()):
        raise ValueError(f"Invalid pair symbol {symbol!r}; currencies must be letters")
    return symbol


def ensure_pairs(session: Session, settings: Settings | None = None) -> list[CurrencyPair]:
    """Create the configured pairs in the database if missing (idempotent)."""
    settings = settings or get_settings()
    existing = {p.symbol: p for p in session.scalars(select(CurrencyPair)).all()}
    created = []
    for i, symbol in enumerate(settings.pairs_list):
        if symbol in existing:
            continue
        base, quote = symbol.split("/")
        pair = CurrencyPair(
            symbol=symbol,
            base=base,
            quote=quote,
            display_name_fa=PAIR_NAMES_FA.get(symbol, symbol),
            is_active=True,
            sort_order=i,
        )
        session.add(pair)
        created.append(pair)
    if created:
        session.commit()
        logger.info("Created %d currency pairs", len(created))
    return created


def _naive_utc(ts: datetime) -> datetime:
    """Normalize to naive UTC for reliable comparisons with SQLite-stored values."""
    if isinstance(ts, date) and not isinstance(ts, datetime):
        ts = datetime(ts.year, ts.month, ts.day)
    if ts.tzinfo is not None:
        return ts.astimezone(timezone.utc).replace(tzinfo=None)
    return ts


def upsert_bars(
    session: Session,
    pair_symbol: str,
    bars: Iterable[PriceBarData],
    data_source: str,
    dataset_version: str | None = None,
) -> int:
    """Insert bars with de-duplication on (pair, timestamp, interval, data_source).

    Returns the number of newly inserted bars. Robust against concurrent
    collectors: unique-constraint conflicts are skipped, not raised.
    Every inserted bar carries provenance (fetched_at, dataset_version,
    quality_flag). The Parquet series mirror is refreshed after the commit.
    """
    is_demo = data_source == "demo"
    fetched_at = datetime.now(timezone.utc)
    dataset_version = dataset_version or f"{data_source}:{fetched_at.date().isoformat()}"
    inserted = 0
    existing_keys = {
        _naive_utc(ts)
        for ts in session.execute(
            select(PriceBar.timestamp).where(
                PriceBar.pair_symbol == pair_symbol,
                PriceBar.interval == "1d",
                PriceBar.data_source == data_source,
            )
        )
        .scalars()
        .all()
    }

    pending = []
    for bar in bars:
        key = _naive_utc(bar.timestamp)
        if key in existing_keys:
            continue
        existing_keys.add(key)
        pending.append(bar)

    # Bulk-insert in chunks; on a unique-conflict, retry that chunk row by row.
    chunk_size = 500
    for i in range(0, len(pending), chunk_size):
        chunk = pending[i : i + chunk_size]
        rows = [
            PriceBar(
                pair_symbol=pair_symbol,
                timestamp=bar.timestamp,
                interval="1d",
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
                data_source=data_source,
                is_demo=is_demo,
                fetched_at=fetched_at,
                dataset_version=dataset_version,
                quality_flag="ok",
            )
            for bar in chunk
        ]
        try:
            with session.begin_nested():
                session.add_all(rows)
                session.flush()
            inserted += len(rows)
        except IntegrityError:
            for row in rows:
                try:
                    with session.begin_nested():
                        session.add(row)
                        session.flush()
                    inserted += 1
                except IntegrityError:
                    continue
    session.commit()
    if inserted:
        try:
            sync_series_mirror(session, pair_symbol, data_source)
        except Exception as exc:
            logger.warning("Series mirror sync failed for %s/%s: %s", pair_symbol, data_source, exc)
    return inserted


def sync_series_mirror(session: Session, pair_symbol: str, data_source: str) -> None:
    """Refresh the Parquet mirror for one (pair, source) series."""
    import pandas as pd

    from app.services.storage.series import write_series

    bars = get_history(session, pair_symbol, data_source=data_source)
    if not bars:
        return
    df = pd.DataFrame(
        {
            "timestamp": [b.timestamp for b in bars],
            "open": [b.open for b in bars],
            "high": [b.high for b in bars],
            "low": [b.low for b in bars],
            "close": [b.close for b in bars],
            "volume": [b.volume for b in bars],
            "quality_flag": [b.quality_flag for b in bars],
            "dataset_version": [b.dataset_version for b in bars],
        }
    )
    write_series(df, pair_symbol, data_source)


def collect_data(
    session: Session,
    settings: Settings | None = None,
    pairs: list[str] | None = None,
    start: date | None = None,
    end: date | None = None,
) -> dict:
    """Fetch history for the given (or all) pairs and persist it.

    Returns a summary dict: per-pair inserted counts, the data source that was
    actually used, and whether the demo fallback was exercised.
    """
    settings = settings or get_settings()
    ensure_pairs(session, settings)
    provider = get_provider(settings)
    end = end or date.today()
    start = start or (end - timedelta(days=settings.history_days))

    targets = [validate_pair_symbol(p) for p in pairs] if pairs else list(settings.pairs_list)
    summary: dict = {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "pairs": {},
        "data_source": provider.name,
        "fallback_used": False,
    }
    for symbol in targets:
        bars = provider.fetch_history(symbol, start, end)
        inserted = upsert_bars(session, symbol, bars, provider.name)
        summary["pairs"][symbol] = {"fetched": len(bars), "inserted": inserted}
        logger.info(
            "collect_data %s: fetched=%d inserted=%d source=%s",
            symbol,
            len(bars),
            inserted,
            provider.name,
        )

    summary["data_source"] = getattr(provider, "last_source", provider.name)
    summary["fallback_used"] = bool(getattr(provider, "fallback_used", False))
    return summary


def get_history(
    session: Session,
    pair_symbol: str,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int | None = None,
    data_source: str | None = None,
) -> list[PriceBar]:
    """Return bars for a pair (chronological). If data_source is None, use the pair's active source."""
    pair_symbol = validate_pair_symbol(pair_symbol)
    if data_source is None:
        data_source = get_active_source(session, pair_symbol) or "demo"
    stmt = select(PriceBar).where(
        PriceBar.pair_symbol == pair_symbol,
        PriceBar.interval == "1d",
        PriceBar.data_source == data_source,
    )
    if start is not None:
        stmt = stmt.where(PriceBar.timestamp >= start)
    if end is not None:
        stmt = stmt.where(PriceBar.timestamp <= end)
    stmt = stmt.order_by(PriceBar.timestamp.asc())
    if limit is not None and limit > 0:
        # keep the most recent `limit` rows but return them chronologically
        sub = (
            select(PriceBar)
            .where(
                PriceBar.pair_symbol == pair_symbol,
                PriceBar.interval == "1d",
                PriceBar.data_source == data_source,
            )
            .order_by(PriceBar.timestamp.desc())
            .limit(limit)
            .subquery()
        )
        stmt = (
            select(PriceBar).join(sub, PriceBar.id == sub.c.id).order_by(PriceBar.timestamp.asc())
        )
    return list(session.scalars(stmt).all())


def get_active_source(session: Session, pair_symbol: str) -> str | None:
    """Data source of the most recent bar for the pair (the 'active' source)."""
    row = session.execute(
        select(PriceBar.data_source)
        .where(PriceBar.pair_symbol == pair_symbol, PriceBar.interval == "1d")
        .order_by(PriceBar.timestamp.desc(), PriceBar.id.desc())
        .limit(1)
    ).first()
    return row[0] if row else None


def get_latest_bar(session: Session, pair_symbol: str) -> PriceBar | None:
    pair_symbol = validate_pair_symbol(pair_symbol)
    source = get_active_source(session, pair_symbol)
    if source is None:
        return None
    return session.scalars(
        select(PriceBar)
        .where(
            PriceBar.pair_symbol == pair_symbol,
            PriceBar.interval == "1d",
            PriceBar.data_source == source,
        )
        .order_by(PriceBar.timestamp.desc(), PriceBar.id.desc())
        .limit(1)
    ).first()


def get_previous_bar(session: Session, pair_symbol: str) -> PriceBar | None:
    pair_symbol = validate_pair_symbol(pair_symbol)
    source = get_active_source(session, pair_symbol)
    if source is None:
        return None
    rows = list(
        session.scalars(
            select(PriceBar)
            .where(
                PriceBar.pair_symbol == pair_symbol,
                PriceBar.interval == "1d",
                PriceBar.data_source == source,
            )
            .order_by(PriceBar.timestamp.desc(), PriceBar.id.desc())
            .limit(2)
        ).all()
    )
    return rows[1] if len(rows) > 1 else None


def count_bars(session: Session) -> int:
    return int(session.scalar(select(func.count(PriceBar.id))) or 0)


def pairs_overview(session: Session) -> list[tuple[CurrencyPair, PriceBar | None]]:
    """All active pairs with their latest bar (may be None)."""
    result = []
    for pair in session.scalars(
        select(CurrencyPair)
        .where(CurrencyPair.is_active.is_(True))
        .order_by(CurrencyPair.sort_order)
    ).all():
        result.append((pair, get_latest_bar(session, pair.symbol)))
    return result
