from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from trading_agent.replay.analysis import collect_paper_orders, discover_run_dates
from trading_agent.replay.forward_returns import PriceLoader, _entry_index, default_price_loader

_FILLED = {"filled", "partial_filled"}


def setup_outcomes(
    agent_root: Path,
    *,
    lookahead: int = 5,
    since: str | None = None,
    until: str | None = None,
    price_loader: PriceLoader = default_price_loader,
) -> list[dict[str, Any]]:
    """Per setup_type (pullback / breakout / …), of the filled buys, how many reached `target_1`
    before `stop_price` within `lookahead` trading days. Close-based approximation (the loader
    returns daily closes), so it slightly understates intraday touches but is directionally
    correct — the key question is which setup actually wins.

    Returns one row per setup_type: fills / target_first / stop_first / undecided + win_rate."""
    run_dates = discover_run_dates(agent_root, since_date=since, until_date=until)
    if not run_dates:
        return []
    orders = collect_paper_orders(agent_root, run_dates=run_dates)

    symbols = {str(o.get("symbol") or "").upper() for o in orders if o.get("symbol")}
    if not symbols:
        return []
    start = min(run_dates)
    from datetime import date, timedelta
    end = (date.fromisoformat(max(run_dates)) + timedelta(days=lookahead * 2 + 7)).isoformat()
    series = {sym: price_loader(sym, start, end) for sym in symbols}

    agg: dict[str, dict[str, int]] = defaultdict(lambda: {"fills": 0, "target_first": 0, "stop_first": 0, "undecided": 0})
    for order in orders:
        if str(order.get("status") or "").lower() not in _FILLED or str(order.get("side") or "").lower() != "buy":
            continue
        setup_type = str(order.get("setup_type") or "unknown")
        target = order.get("target_1")
        stop = order.get("stop_price")
        symbol = str(order.get("symbol") or "").upper()
        run_date = str(order.get("_run_date") or "")
        if target is None or stop is None or not symbol or not run_date:
            continue
        agg[setup_type]["fills"] += 1
        bars = series.get(symbol) or []
        entry_idx = _entry_index(bars, run_date)
        if entry_idx is None:
            agg[setup_type]["undecided"] += 1
            continue
        outcome = "undecided"
        for bar in bars[entry_idx + 1: entry_idx + 1 + lookahead]:
            close = bar[1]
            if close >= float(target):
                outcome = "target_first"
                break
            if close <= float(stop):
                outcome = "stop_first"
                break
        agg[setup_type][outcome] += 1

    rows: list[dict[str, Any]] = []
    for setup_type, data in sorted(agg.items()):
        decided = data["target_first"] + data["stop_first"]
        rows.append({
            "setup_type": setup_type,
            "fills": data["fills"],
            "target_first": data["target_first"],
            "stop_first": data["stop_first"],
            "undecided": data["undecided"],
            "win_rate": round(data["target_first"] / decided, 4) if decided else None,
        })
    return rows
