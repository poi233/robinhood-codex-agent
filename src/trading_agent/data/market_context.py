from __future__ import annotations

import os
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from trading_agent.core.io import ensure_dir, write_json
from trading_agent.data.charts import write_chart
from trading_agent.data.providers.yfinance_provider import jsonable, normalize_news_item
from trading_agent.data.universe import parse_universe

TIMEFRAME_MAP = {
    "1w": {"label": "weekly", "days": 180, "step_days": 7},
    "1d": {"label": "daily", "days": 120, "step_days": 1},
    "1h": {"label": "hourly", "days": 20, "step_days": 1},
    "15m": {"label": "intraday_15m", "days": 10, "step_days": 1},
}


@dataclass
class SymbolArtifacts:
    ohlcv: str
    charts: str
    news: str
    earnings: str
    filings: str
    notes: str = ""


def build_mock_rows(run_date: date, timeframe: str) -> list[dict[str, object]]:
    config = TIMEFRAME_MAP[timeframe]
    periods = 40
    start = run_date - timedelta(days=config["days"])
    rows: list[dict[str, object]] = []
    price = 100.0

    for index in range(periods):
        current_day = start + timedelta(days=index * config["step_days"])
        if timeframe in {"1h", "15m"}:
            timestamp = datetime.combine(current_day, time(9, 30), tzinfo=timezone.utc) + timedelta(minutes=index * 15)
        else:
            timestamp = datetime.combine(current_day, time(0, 0), tzinfo=timezone.utc)

        open_price = price + (index % 3) * 0.4
        close_price = open_price + 0.6
        high_price = close_price + 0.5
        low_price = open_price - 0.7
        volume = 1_000_000 + index * 5_000
        rows.append(
            {
                "timestamp": timestamp.isoformat(),
                "open": round(open_price, 2),
                "high": round(high_price, 2),
                "low": round(low_price, 2),
                "close": round(close_price, 2),
                "volume": volume,
            }
        )
        price += 0.8

    return rows


_INTERVAL_MAP = {"1w": "1wk", "1d": "1d", "1h": "60m", "15m": "15m"}
_PERIOD_MAP = {"1w": "3y", "1d": "1y", "1h": "60d", "15m": "30d"}


def _frame_to_rows(frame: Any) -> list[dict[str, object]]:
    """Convert a yfinance OHLCV frame into our row dicts, skipping fully-empty rows (which appear for
    a symbol's gaps in a multi-ticker batch download)."""
    rows: list[dict[str, object]] = []
    for idx, row in frame.iterrows():
        try:
            close = row["Close"]
            if close != close:  # NaN (no data for this symbol at this bar)
                continue
            rows.append(
                {
                    "timestamp": idx.isoformat() if hasattr(idx, "isoformat") else str(idx),
                    "open": round(float(row["Open"]), 4),
                    "high": round(float(row["High"]), 4),
                    "low": round(float(row["Low"]), 4),
                    "close": round(float(close), 4),
                    "volume": int(row["Volume"]) if row["Volume"] == row["Volume"] else 0,
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    return rows


def fetch_live_rows(symbol: str, timeframe: str, *, period: str | None = None) -> list[dict[str, object]]:
    try:
        import yfinance as yf
    except Exception as exc:
        raise RuntimeError(f"yfinance import failed: {exc}") from exc

    interval = _INTERVAL_MAP[timeframe]
    period = period or _PERIOD_MAP[timeframe]
    frame = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=False)
    if frame.empty:
        raise RuntimeError(f"empty history for {symbol} {timeframe}")
    return _frame_to_rows(frame)


def _rows_from_download_frame(frame: Any, symbols: list[str]) -> dict[str, list[dict[str, object]]]:
    """Split a multi-ticker yf.download frame into per-symbol rows. Tolerates the single-ticker
    (flat columns) and multi-ticker (MultiIndex columns) shapes, and symbols missing from the frame."""
    import pandas as pd

    if frame is None or getattr(frame, "empty", True):
        return {s: [] for s in symbols}
    multi = isinstance(frame.columns, pd.MultiIndex)
    out: dict[str, list[dict[str, object]]] = {}
    for symbol in symbols:
        try:
            sub = frame[symbol] if multi else frame
        except KeyError:
            out[symbol] = []
            continue
        out[symbol] = _frame_to_rows(sub)
    return out


def fetch_live_rows_batch(symbols: list[str], timeframe: str, *, period: str | None = None) -> dict[str, list[dict[str, object]]]:
    """D2: fetch OHLCV for many symbols in ONE yf.download call instead of one Ticker().history per
    symbol — far fewer round trips on a multi-symbol universe. Returns {symbol: rows} ([] per symbol
    with no data). Cross-run-date caching (ohlcv_cache) still applies per symbol on top of this."""
    requested = [str(s).upper() for s in symbols if str(s).strip()]
    if not requested:
        return {}
    try:
        import yfinance as yf
    except Exception as exc:
        raise RuntimeError(f"yfinance import failed: {exc}") from exc
    interval = _INTERVAL_MAP[timeframe]
    period = period or _PERIOD_MAP[timeframe]
    frame = yf.download(tickers=requested, period=period, interval=interval, auto_adjust=False,
                        group_by="ticker", progress=False, threads=True)
    return _rows_from_download_frame(frame, requested)


def build_mock_news_payload(symbol: str, run_date: str, limit: int) -> dict[str, object]:
    return {
        "symbol": symbol,
        "date": run_date,
        "headlines": [
            {
                "title": f"Mock catalyst item {index + 1} for {symbol}",
                "source": "mock_source",
                "published_at": f"{run_date}T06:{index:02d}:00-0700",
            }
            for index in range(limit)
        ],
        "earnings": {"status": "ok", "next_event": None},
        "filings": {"status": "ok", "items": []},
    }


def build_live_news_payload(symbol: str, run_date: str, limit: int) -> dict[str, object]:
    try:
        import yfinance as yf
    except Exception as exc:
        raise RuntimeError(f"yfinance import failed: {exc}") from exc

    ticker = yf.Ticker(symbol)
    try:
        raw_news = ticker.news or []
        news_status = "ok"
        news_error = ""
    except Exception as exc:
        raw_news = []
        news_status = "failed"
        news_error = str(exc)
    headlines = []
    for item in raw_news[:limit]:
        normalized = normalize_news_item(item)
        if normalized:
            headlines.append(normalized)

    try:
        calendar = jsonable(ticker.calendar or {})
    except Exception as exc:
        calendar = {"status": "failed", "error": str(exc)}

    try:
        filings = jsonable(ticker.sec_filings or [])
        filing_status = "ok"
    except Exception as exc:
        filings = []
        filing_status = "failed"
        filing_error = str(exc)
    else:
        filing_error = ""

    return {
        "symbol": symbol,
        "date": run_date,
        "headlines": headlines,
        "news": {"status": news_status, "error": news_error},
        "earnings": {"status": "ok", "calendar": calendar},
        "filings": {"status": filing_status, "items": filings[:limit], "error": filing_error},
    }


def build_news_payload(symbol: str, run_date: str, limit: int, mock: bool) -> dict[str, object]:
    if mock:
        return build_mock_news_payload(symbol, run_date, limit)
    return build_live_news_payload(symbol, run_date, limit)


def _process_one_symbol(
    symbol: str,
    date_value: date,
    run_date: str,
    timeframes: list[str],
    news_limit: int,
    mock: bool,
    output_dir: Path,
    cache_dir: Path | None = None,
    prefetched_rows: dict[str, dict[str, list]] | None = None,
) -> tuple[str, dict[str, str], bool]:
    notes: list[str] = []
    ohlcv_status = "ok"
    chart_status = "ok"
    news_status = "ok"
    earnings_status = "ok"
    filings_status = "ok"

    try:
        for timeframe in timeframes:
            label = TIMEFRAME_MAP[timeframe]["label"]
            if mock:
                rows = build_mock_rows(date_value, timeframe)
            elif (prefetched_rows is not None
                  and symbol in prefetched_rows
                  and timeframe in prefetched_rows[symbol]):
                rows = prefetched_rows[symbol][timeframe]
            elif cache_dir is not None:
                from trading_agent.data.ohlcv_cache import fetch_cached_rows

                rows = fetch_cached_rows(symbol, timeframe, date_value, cache_dir)
            else:
                rows = fetch_live_rows(symbol, timeframe)
            write_json(output_dir / "ohlcv" / symbol / f"{label}.json", rows)
            write_chart(rows, output_dir / "charts" / symbol / f"{label}.png", f"{symbol} {label}")
    except Exception as exc:
        ohlcv_status = "failed"
        chart_status = "failed"
        notes.append(str(exc))

    try:
        news_payload = build_news_payload(symbol, run_date, news_limit, mock)
        write_json(output_dir / "news" / f"{symbol}.json", news_payload)
        if not mock:
            news_status = str((news_payload.get("news") or {}).get("status", "ok"))
            earnings_status = str((news_payload.get("earnings") or {}).get("status", "ok"))
            filings_status = str((news_payload.get("filings") or {}).get("status", "ok"))
            if news_status != "ok":
                notes.append(str((news_payload.get("news") or {}).get("error", "news fetch failed")))
            if earnings_status != "ok":
                notes.append(str((news_payload.get("earnings") or {}).get("error", "earnings fetch failed")))
            if filings_status != "ok":
                notes.append(str((news_payload.get("filings") or {}).get("error", "filings fetch failed")))
    except Exception as exc:
        news_status = "failed"
        earnings_status = "failed"
        filings_status = "failed"
        notes.append(str(exc))

    status = SymbolArtifacts(
        ohlcv_status,
        chart_status,
        news_status,
        earnings_status,
        filings_status,
        "; ".join(note for note in notes if note),
    ).__dict__
    return symbol, status, ohlcv_status == "ok" and chart_status == "ok"


def _prefetch_ohlcv_batch(
    symbols: list[str],
    timeframes: list[str],
) -> dict[str, dict[str, list]] | None:
    """D2: pre-fetch OHLCV for all symbols in one yf.download per timeframe.

    Returns {symbol: {timeframe: rows}} on success, None on any batch failure (caller falls
    back to per-symbol fetch). Used when cache is disabled — the per-symbol cache path handles
    its own incremental pull.
    """
    prefetched: dict[str, dict[str, list]] = {}
    try:
        for timeframe in timeframes:
            batch = fetch_live_rows_batch(symbols, timeframe)
            for sym, rows in batch.items():
                prefetched.setdefault(sym, {})[timeframe] = rows
    except Exception:
        return None  # any failure → caller uses per-symbol fallback
    return prefetched


def collect_market_context(
    universe_file: Path,
    output_dir: Path,
    run_date: str,
    timeframes: list[str],
    news_limit: int,
    mock: bool,
    symbols: list[str] | None = None,
    cache_dir: Path | None = None,
) -> dict[str, object]:
    date_value = date.fromisoformat(run_date)
    requested_symbols = symbols if symbols is not None else parse_universe(universe_file)
    requested_set = set(requested_symbols)

    # Selectively remove stale symbol dirs (symbols no longer in the run)
    # rather than rmtree-ing the entire output dir every time.
    for subdir in ("ohlcv", "charts"):
        base = output_dir / subdir
        if base.exists():
            for sym_dir in base.iterdir():
                if sym_dir.is_dir() and sym_dir.name not in requested_set:
                    shutil.rmtree(sym_dir)

    ensure_dir(output_dir)
    ensure_dir(output_dir / "charts")
    ensure_dir(output_dir / "ohlcv")
    ensure_dir(output_dir / "news")

    # D2: batch-prefetch OHLCV for all symbols in one yf.download per timeframe when no
    # per-symbol cache is active. Falls back to None (per-symbol fetch) on any failure.
    prefetched_rows: dict[str, dict[str, list]] | None = None
    if not mock and cache_dir is None:
        prefetched_rows = _prefetch_ohlcv_batch(requested_symbols, timeframes)

    completed_symbols: list[str] = []
    failed_symbols: list[str] = []
    symbol_status: dict[str, dict[str, str]] = {}

    max_workers = int(os.environ.get("MARKET_FEED_MAX_WORKERS", "4") or "4")
    with ThreadPoolExecutor(max_workers=min(max_workers, max(1, len(requested_symbols)))) as executor:
        futures = {
            executor.submit(
                _process_one_symbol, sym, date_value, run_date, timeframes, news_limit, mock,
                output_dir, cache_dir, prefetched_rows
            ): sym
            for sym in requested_symbols
        }
        for future in as_completed(futures):
            sym, status, is_complete = future.result()
            symbol_status[sym] = status
            if is_complete:
                completed_symbols.append(sym)
            else:
                failed_symbols.append(sym)

    market_summary = {
        "date": run_date,
        "requested_symbols": requested_symbols,
        "completed_symbols": completed_symbols,
        "failed_symbols": failed_symbols,
        "summary": "mock market summary" if mock else "public market summary",
    }
    write_json(output_dir / "news" / "market_summary.json", market_summary)

    manifest = {
        "date": run_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_mode": "manual" if mock else "scheduled",
        "source_universe": str(universe_file),
        "requested_symbols": requested_symbols,
        "completed_symbols": completed_symbols,
        "failed_symbols": failed_symbols,
        "timeframes": timeframes,
        "sources": {
            "ohlcv": "mock" if mock else "yfinance",
            "news": "mock" if mock else "yfinance",
            "earnings": "mock" if mock else "yfinance",
            "filings": "mock" if mock else "yfinance",
        },
        "data_status": (
            "failed"
            if not completed_symbols
            else (
                "partial"
                if failed_symbols
                or any(status != "ok" for item in symbol_status.values() for key, status in item.items() if key != "notes")
                else "ok"
            )
        ),
        "artifacts": {
            "charts_root": str(output_dir / "charts"),
            "ohlcv_root": str(output_dir / "ohlcv"),
            "news_root": str(output_dir / "news"),
        },
        "symbol_status": symbol_status,
        "notes": "mock artifact bundle" if mock else "live artifact bundle",
    }
    write_json(output_dir / "manifest.json", manifest)
    return manifest
