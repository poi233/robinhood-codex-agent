from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import read_json, write_json
from trading_agent.core.time import PT


def _selected_symbols(candidate_snapshot: dict[str, Any]) -> list[str]:
    symbols: list[str] = []
    for symbol in candidate_snapshot.get("selected_symbols", []):
        normalized = str(symbol or "").upper().strip()
        if normalized and normalized not in symbols:
            symbols.append(normalized)
    return symbols


def _read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = read_json(path)
    return payload if isinstance(payload, list) else []


def _quote_from_rows(symbol: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    usable = [row for row in rows if isinstance(row, dict) and row.get("close") is not None]
    if not usable:
        return None
    latest = usable[-1]
    previous = usable[-2] if len(usable) >= 2 else usable[-1]
    try:
        last_price = round(float(latest["close"]), 4)
        previous_close = round(float(previous["close"]), 4)
    except (TypeError, ValueError):
        return None
    change_pct = round(((last_price - previous_close) / previous_close) * 100, 4) if previous_close else 0.0
    return {
        "last_price": last_price,
        "previous_close": previous_close,
        "change_pct": change_pct,
        "updated_at": latest.get("timestamp"),
        "source": "market_feed:daily",
        "symbol": symbol,
    }


def build_candidate_quote_snapshot(
    *,
    run_date: str,
    candidate_snapshot: dict[str, Any],
    market_feed_dir: Path,
) -> dict[str, Any]:
    symbols = _selected_symbols(candidate_snapshot)
    quotes: dict[str, Any] = {}
    missing: list[str] = []
    for symbol in symbols:
        quote = _quote_from_rows(symbol, _read_rows(market_feed_dir / "ohlcv" / symbol / "daily.json"))
        if quote is None:
            missing.append(symbol)
        else:
            quotes[symbol] = quote
    if not symbols:
        data_status = "ok"
    elif quotes and missing:
        data_status = "partial"
    elif quotes:
        data_status = "ok"
    else:
        data_status = "failed"
    return {
        "date": run_date,
        "generated_at": datetime.now(tz=PT).isoformat(),
        "data_status": data_status,
        "symbols": quotes,
        "missing_symbols": missing,
        "notes": "Candidate quotes derived deterministically from local market_feed daily OHLCV artifacts.",
    }


def build_candidate_quote_snapshot_from_paths(agent_root: Path, run_date: str) -> dict[str, Any]:
    paths = build_runtime_paths(agent_root, run_date=run_date)
    candidate_snapshot = read_json(paths.candidate_snapshot_path) if paths.candidate_snapshot_path.exists() else {}
    payload = build_candidate_quote_snapshot(
        run_date=run_date,
        candidate_snapshot=candidate_snapshot if isinstance(candidate_snapshot, dict) else {},
        market_feed_dir=paths.market_feed_dir,
    )
    write_json(paths.quote_snapshot_candidates_path, payload)
    return payload

