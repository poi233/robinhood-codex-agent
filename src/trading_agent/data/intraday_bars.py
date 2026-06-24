"""Q6 — intraday bar capture (the data layer that lifts the daily-close ceiling).

The setup screener (Q1) and ``setup_outcomes`` only have daily closes, so intraday-timing setups
(opening-range breakout, VWAP reclaim) can't be backtested — only forward-papered slowly. This
module captures, every intraday tick, the per-symbol price the engine already fetched, appending it
to ``runtime/state/runs/<date>/intraday_bars.jsonl``. Over a session that builds an intraday price
path per symbol that intraday setups + a future intraday PriceLoader can use.

Capture is opt-in behind ``ENABLE_INTRADAY_BAR_CAPTURE`` (gated at the call site in the intraday
pipeline, since it adds per-tick I/O to the hot path). Reading is always safe: ``load_intraday_bars``
returns ``{}`` when the file is absent, so the new intraday setups simply stay dormant until capture
has been running. Additive only — never touches champion scoring / paper / decision state.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_agent.core.context import build_runtime_paths


def _intraday_bars_path(agent_root: Path, *, run_date: str, paths_override: Any | None = None) -> Path:
    run_state_dir = paths_override.run_state_dir if paths_override is not None else build_runtime_paths(agent_root, run_date=run_date).run_state_dir
    return run_state_dir / "intraday_bars.jsonl"


def capture_intraday_bars(
    agent_root: Path,
    *,
    run_date: str,
    quotes: dict[str, Any],
    timestamp: str | None = None,
    paths_override: Any | None = None,
) -> int:
    """Append one snapshot row per fresh, positive-price quote. Returns the number of rows written.
    Best-effort/additive: one tick is one batch of ``{timestamp, symbol, price}`` lines."""
    path = _intraday_bars_path(agent_root, run_date=run_date, paths_override=paths_override)
    stamp = timestamp or datetime.now(timezone.utc).isoformat()
    rows: list[str] = []
    for symbol, quote in (quotes or {}).items():
        price = getattr(quote, "price", None)
        if price is None or price <= 0:
            continue
        rows.append(json.dumps({"timestamp": stamp, "symbol": str(symbol).upper(), "price": float(price)}))
    if not rows:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(rows) + "\n")
    return len(rows)


def load_intraday_bars(
    agent_root: Path,
    *,
    run_date: str,
    paths_override: Any | None = None,
) -> dict[str, list[tuple[str, float]]]:
    """Read the captured snapshots → ``{SYMBOL: [(timestamp, price), ...]}`` sorted by time.
    Returns ``{}`` when nothing has been captured (file absent)."""
    path = _intraday_bars_path(agent_root, run_date=run_date, paths_override=paths_override)
    if not path.exists():
        return {}
    by_symbol: dict[str, list[tuple[str, float]]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        symbol = str(row.get("symbol") or "").upper()
        ts = str(row.get("timestamp") or "")
        try:
            price = float(row.get("price"))
        except (TypeError, ValueError):
            continue
        if symbol and ts and price > 0:
            by_symbol.setdefault(symbol, []).append((ts, price))
    for series in by_symbol.values():
        series.sort(key=lambda item: item[0])
    return by_symbol
