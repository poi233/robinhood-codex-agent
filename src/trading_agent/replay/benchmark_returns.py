from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

from trading_agent.replay.analysis import discover_run_dates
from trading_agent.replay.forward_returns import DEFAULT_HORIZONS, PriceLoader, _entry_index, default_price_loader

DEFAULT_BENCHMARKS = ("SPY", "QQQ", "SMH", "IWM")


def compute_benchmark_returns(
    agent_root: Path,
    *,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    benchmarks: tuple[str, ...] = DEFAULT_BENCHMARKS,
    since: str | None = None,
    until: str | None = None,
    price_loader: PriceLoader = default_price_loader,
) -> dict[str, dict[int, dict[str, Any]]]:
    """Mean benchmark forward return per horizon, computed over the same run dates as the
    candidates. Lets the calibration report separate strategy alpha from market beta:
    alpha ≈ candidate-bucket mean return − benchmark mean return at the same horizon."""
    run_dates = discover_run_dates(agent_root, since_date=since, until_date=until)
    if not run_dates:
        return {}
    max_h = max(horizons) if horizons else 5
    start = min(run_dates)
    end = (date.fromisoformat(max(run_dates)) + timedelta(days=max_h * 2 + 7)).isoformat()

    result: dict[str, dict[int, dict[str, Any]]] = {}
    for symbol in benchmarks:
        bars = price_loader(symbol, start, end)
        per_horizon: dict[int, dict[str, Any]] = {}
        for horizon in horizons:
            rets: list[float] = []
            for run_date in run_dates:
                entry_idx = _entry_index(bars, run_date)
                if entry_idx is None or entry_idx + horizon >= len(bars):
                    continue
                entry_close = bars[entry_idx][1]
                if not entry_close:
                    continue
                rets.append(bars[entry_idx + horizon][1] / entry_close - 1)
            per_horizon[horizon] = {
                "count": len(rets),
                "mean_return": round(sum(rets) / len(rets), 6) if rets else None,
            }
        result[symbol] = per_horizon
    return result
