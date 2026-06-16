from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

from trading_agent.core.io import read_json, write_json
from trading_agent.data.market_context import TIMEFRAME_MAP, fetch_live_rows

CACHEABLE_TIMEFRAMES = {"1w", "1d"}
INCREMENTAL_PERIOD = {"1w": "1mo", "1d": "5d"}
SPLIT_DIVIDEND_TOLERANCE = 0.01  # 1% relative close-price tolerance on overlapping bars


def cache_path(cache_dir: Path, symbol: str, timeframe: str) -> Path:
    return cache_dir / symbol / f"{timeframe}.json"


def _load_cached_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = read_json(path)
    rows = payload.get("rows") if isinstance(payload, dict) else None
    return rows if isinstance(rows, list) else []


def _bars_diverge(cached_rows: list[dict[str, Any]], fresh_rows: list[dict[str, Any]]) -> bool:
    """Proxy for a split/dividend adjustment having invalidated the cache:
    compare close price on timestamps present in both lists."""
    fresh_by_ts = {row.get("timestamp"): row for row in fresh_rows}
    for row in cached_rows:
        match = fresh_by_ts.get(row.get("timestamp"))
        if match is None:
            continue
        cached_close = float(row.get("close") or 0)
        fresh_close = float(match.get("close") or 0)
        if cached_close <= 0:
            continue
        if abs(fresh_close - cached_close) / cached_close > SPLIT_DIVIDEND_TOLERANCE:
            return True
    return False


def _merge_rows(
    cached_rows: list[dict[str, Any]],
    fresh_rows: list[dict[str, Any]],
    *,
    window_days: int,
    run_date: date,
) -> list[dict[str, Any]]:
    by_timestamp: dict[Any, dict[str, Any]] = {row.get("timestamp"): row for row in cached_rows}
    by_timestamp.update({row.get("timestamp"): row for row in fresh_rows})
    merged = sorted(by_timestamp.values(), key=lambda row: str(row.get("timestamp")))
    cutoff = (run_date - timedelta(days=window_days)).isoformat()
    return [row for row in merged if str(row.get("timestamp")) >= cutoff]


def fetch_cached_rows(symbol: str, timeframe: str, run_date: date, cache_dir: Path) -> list[dict[str, Any]]:
    """OHLCV rows for `timeframe`, using a cross-run-date cache for 1w/1d bars.

    1w/1d history barely changes day to day, so instead of re-fetching the
    full lookback window (1y/3y) every run, this reuses yesterday's cached
    rows and only fetches a short incremental tail. Falls back to a full
    fetch (rewriting the cache) when there's no cache yet, or when
    overlapping bars diverge beyond SPLIT_DIVIDEND_TOLERANCE -- a proxy for a
    split/dividend adjustment having invalidated the cached prices. 1h/15m
    are not cached: they're not in scope here and change too fast to benefit.
    """
    if timeframe not in CACHEABLE_TIMEFRAMES:
        return fetch_live_rows(symbol, timeframe)

    path = cache_path(cache_dir, symbol, timeframe)
    cached_rows = _load_cached_rows(path)
    window_days = TIMEFRAME_MAP[timeframe]["days"]

    if not cached_rows:
        fresh_rows = fetch_live_rows(symbol, timeframe)
        write_json(path, {"symbol": symbol, "timeframe": timeframe, "rows": fresh_rows})
        return fresh_rows

    incremental_rows = fetch_live_rows(symbol, timeframe, period=INCREMENTAL_PERIOD[timeframe])
    if _bars_diverge(cached_rows, incremental_rows):
        fresh_rows = fetch_live_rows(symbol, timeframe)
        write_json(path, {"symbol": symbol, "timeframe": timeframe, "rows": fresh_rows})
        return fresh_rows

    merged_rows = _merge_rows(cached_rows, incremental_rows, window_days=window_days, run_date=run_date)
    write_json(path, {"symbol": symbol, "timeframe": timeframe, "rows": merged_rows})
    return merged_rows
