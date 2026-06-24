"""Q5 — multiple-comparison guardrails (don't get fooled by screening many strategies).

Screening N setups over the same history is the multiple-comparisons trap: the more candidates you
test, the more likely one looks great by luck. This module supplies the statistics to keep that
honest, all dependency-free (no scipy/numpy):

  - ``binomial_sf`` — one-sided p-value that a setup's win rate beats a coin flip (exact binomial),
    so "67% win rate" on 6 trades is correctly treated as unconvincing.
  - ``benjamini_hochberg`` — False Discovery Rate control across the N screened setups: which
    setups stay significant once you account for having tested many.
  - ``sharpe`` / ``max_drawdown_from_returns`` / ``combine_equal_weight_returns`` — portfolio-level
    evaluation: judge the *combination* of the diverse picks (a low-correlation mediocre strategy
    can lift the portfolio Sharpe), not each strategy in isolation.

Pure functions; the screener (Q1) and recommend (Q2) call in.
"""
from __future__ import annotations

from math import comb, sqrt
from typing import Any

TRADING_DAYS_PER_YEAR = 252


def binomial_sf(wins: int, n: int, p0: float = 0.5) -> float | None:
    """One-sided p-value P(X >= wins) for X ~ Binomial(n, p0): the chance of seeing at least this
    many wins if the setup were really a ``p0`` coin. None when n == 0. Lower = more convincing."""
    if n <= 0 or wins <= 0:
        return None if n <= 0 else 1.0
    wins = min(wins, n)
    tail = sum(comb(n, k) * (p0 ** k) * ((1.0 - p0) ** (n - k)) for k in range(wins, n + 1))
    return round(min(1.0, max(0.0, tail)), 6)


def benjamini_hochberg(pvalues: dict[str, float], alpha: float = 0.05) -> dict[str, dict[str, Any]]:
    """Benjamini-Hochberg FDR control. Returns per id {p, q, significant} where q is the adjusted
    p-value and ``significant`` means it survives FDR at ``alpha`` across all tested ids."""
    items = [(k, v) for k, v in pvalues.items() if v is not None]
    m = len(items)
    if m == 0:
        return {k: {"p": None, "q": None, "significant": False} for k in pvalues}
    items.sort(key=lambda kv: kv[1])
    # Step-up adjusted q-values: q_(i) = min_{j>=i} (m/j) * p_(j), capped at 1, monotone.
    qs: list[float] = [0.0] * m
    running_min = 1.0
    for i in range(m - 1, -1, -1):
        rank = i + 1
        running_min = min(running_min, (m / rank) * items[i][1])
        qs[i] = min(1.0, running_min)
    # Largest rank with p_(i) <= (i/m)*alpha → everything up to it is significant.
    max_sig_rank = 0
    for i in range(m):
        if items[i][1] <= ((i + 1) / m) * alpha:
            max_sig_rank = i + 1
    out: dict[str, dict[str, Any]] = {}
    for i, (key, p) in enumerate(items):
        out[key] = {"p": round(p, 6), "q": round(qs[i], 6), "significant": (i + 1) <= max_sig_rank}
    for key in pvalues:
        out.setdefault(key, {"p": None, "q": None, "significant": False})
    return out


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean = _mean(values)
    return sqrt(sum((v - mean) ** 2 for v in values) / (n - 1))


def sharpe(returns: list[float], *, periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float | None:
    """Annualised Sharpe of a daily return series (risk-free 0). None if < 2 points or zero vol."""
    if len(returns) < 2:
        return None
    sd = _std(returns)
    if sd == 0:
        return None
    return round(_mean(returns) / sd * sqrt(periods_per_year), 4)


def max_drawdown_from_returns(returns_by_day: dict[str, float]) -> float | None:
    """Max peak-to-trough fractional decline of the cumulative-return equity curve (0.0 = none)."""
    days = sorted(returns_by_day)
    if len(days) < 2:
        return None
    equity = 1.0
    peak = 1.0
    mdd = 0.0
    for day in days:
        equity *= 1.0 + returns_by_day[day]
        peak = max(peak, equity)
        if peak > 0:
            mdd = max(mdd, (peak - equity) / peak)
    return round(mdd, 4)


def combine_equal_weight_returns(
    returns_by_strategy: dict[str, dict[str, float]],
    ids: list[str],
) -> dict[str, float]:
    """Equal-weight portfolio daily return: each day, average the returns of whichever selected
    strategies traded that day. Days with no selected strategy are omitted."""
    by_day: dict[str, list[float]] = {}
    for sid in ids:
        for day, ret in (returns_by_strategy.get(sid) or {}).items():
            by_day.setdefault(day, []).append(ret)
    return {day: _mean(vals) for day, vals in by_day.items() if vals}


def portfolio_metrics(
    returns_by_strategy: dict[str, dict[str, float]],
    ids: list[str],
) -> dict[str, Any]:
    """Sharpe + max drawdown + cumulative return of the equal-weight combination of ``ids``."""
    combined = combine_equal_weight_returns(returns_by_strategy, ids)
    days = sorted(combined)
    cumulative = 1.0
    for day in days:
        cumulative *= 1.0 + combined[day]
    return {
        "strategies": list(ids),
        "days": len(days),
        "sharpe": sharpe([combined[d] for d in days]),
        "max_drawdown": max_drawdown_from_returns(combined),
        "cumulative_return": round(cumulative - 1.0, 6) if days else None,
    }
