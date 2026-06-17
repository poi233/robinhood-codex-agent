from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_agent.core.io import read_json, write_json
from trading_agent.features.factors_price import FACTORS, FactorContext, compute_factors


def _series(bars: list[dict[str, Any]], key: str) -> list[float]:
    out: list[float] = []
    for bar in bars:
        try:
            out.append(float(bar[key]))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def factor_context_from_bars(bars: list[dict[str, Any]], benchmark_bars: list[dict[str, Any]] | None) -> FactorContext:
    return FactorContext(
        closes=_series(bars, "close"),
        highs=_series(bars, "high"),
        lows=_series(bars, "low"),
        volumes=_series(bars, "volume"),
        benchmark_closes=_series(benchmark_bars, "close") if benchmark_bars else None,
    )


def _data_quality(factors: dict[str, Any]) -> str:
    present = sum(1 for v in factors.values() if v is not None)
    if present == 0:
        return "failed"
    if present < len(factors) * 0.5:
        return "partial"
    return "ok"


def build_factor_panel(symbol_bars: dict[str, list[dict[str, Any]]], benchmark_bars: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    """{symbol: {factor_name: value|None, ..., data_quality}} for every symbol. Open dict schema —
    a newly registered factor just adds a key; readers tolerate unknown/missing keys."""
    panel: dict[str, dict[str, Any]] = {}
    for symbol, bars in symbol_bars.items():
        factors = compute_factors(factor_context_from_bars(bars, benchmark_bars))
        factors["data_quality"] = _data_quality(factors)
        panel[str(symbol).upper()] = factors
    return panel


def build_factor_panel_payload(panel: dict[str, dict[str, Any]], *, run_date: str, benchmark: str) -> dict[str, Any]:
    return {
        "date": run_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "benchmark": benchmark,
        "factors": sorted(FACTORS.keys()),
        "symbols": panel,
    }


def build_factor_alpha_payload(alpha: dict[str, dict[str, Any]], *, run_date: str, profile_name: str) -> dict[str, Any]:
    return {
        "date": run_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "profile": profile_name,
        "symbols": alpha,
    }


def load_daily_bars(market_feed_dir: Path, symbol: str) -> list[dict[str, Any]]:
    """Daily OHLCV bars (oldest→newest) for a symbol from market_feed/ohlcv/<symbol>/daily.json. []"""
    path = market_feed_dir / "ohlcv" / symbol / "daily.json"
    if not path.exists():
        return []
    rows = read_json(path)
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def build_and_write_factor_layer(
    agent_root: Path,
    run_date: str,
    *,
    active_symbols: list[str],
    benchmark: str = "SPY",
    profile_name: str | None = None,
) -> tuple[Path, Path]:
    """Read each active symbol's + the benchmark's daily OHLCV from market_feed, build the factor
    panel + factor_alpha, and write factor_panel.json + factor_alpha.json. Read-only w.r.t. trading:
    only writes these two new artifacts; never touches scoring/paper/decisions. Returns the paths."""
    from trading_agent.analyzers.factor_alpha import compute_factor_alpha, load_factor_profile
    from trading_agent.core.context import build_runtime_paths

    paths = build_runtime_paths(agent_root, run_date=run_date)
    market_feed_dir = paths.market_feed_dir
    symbol_bars = {sym: load_daily_bars(market_feed_dir, sym) for sym in active_symbols}
    symbol_bars = {sym: bars for sym, bars in symbol_bars.items() if bars}
    benchmark_bars = load_daily_bars(market_feed_dir, benchmark)

    panel = build_factor_panel(symbol_bars, benchmark_bars)
    profile = load_factor_profile(agent_root, profile_name=profile_name)
    alpha = compute_factor_alpha(panel, profile)

    write_json(paths.factor_panel_path, build_factor_panel_payload(panel, run_date=run_date, benchmark=benchmark))
    write_json(paths.factor_alpha_path, build_factor_alpha_payload(alpha, run_date=run_date, profile_name=str(profile.get("name"))))
    return paths.factor_panel_path, paths.factor_alpha_path
