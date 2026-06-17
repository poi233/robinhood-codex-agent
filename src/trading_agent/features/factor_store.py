from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

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
