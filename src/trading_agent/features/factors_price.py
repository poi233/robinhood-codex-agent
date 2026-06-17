"""Price/volume quantitative factors (H2).

A registry of pure functions over a symbol's daily OHLCV (plus a benchmark series). Each factor
takes a `FactorContext` and returns a float, or `None` when there isn't enough history — never
raises. **Adding a factor is one function + one `@factor("name")` decorator**; everything
downstream (factor_alpha aggregation, factor_panel persistence, calibration bucketing/IC, the
dashboard) discovers it by name, so the layer stays pluggable.

Pure stdlib (no numpy). Read-only; computes nothing that touches trading decisions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

FactorFn = Callable[["FactorContext"], float | None]

# name -> factor function. Add a factor by decorating it with @factor("name").
FACTORS: dict[str, FactorFn] = {}


def factor(name: str) -> Callable[[FactorFn], FactorFn]:
    def _register(fn: FactorFn) -> FactorFn:
        FACTORS[name] = fn
        return fn
    return _register


@dataclass
class FactorContext:
    """Daily series for one symbol (oldest→newest) plus the aligned benchmark closes."""

    closes: list[float]
    highs: list[float]
    lows: list[float]
    volumes: list[float]
    benchmark_closes: list[float] | None = None


# ---- small pure-python math helpers ----

def _returns(series: list[float]) -> list[float]:
    return [series[i] / series[i - 1] - 1 for i in range(1, len(series)) if series[i - 1]]


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    m = _mean(xs)
    return (sum((x - m) ** 2 for x in xs) / (n - 1)) ** 0.5


def _cov(xs: list[float], ys: list[float]) -> float | None:
    n = min(len(xs), len(ys))
    if n < 2:
        return None
    xs, ys = xs[-n:], ys[-n:]
    mx, my = _mean(xs), _mean(ys)
    return sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / (n - 1)


def _cum_return(series: list[float], lookback: int, *, skip: int = 0) -> float | None:
    """Return over [t-lookback, t-skip]; None if not enough bars."""
    if len(series) < lookback + 1:
        return None
    start = series[-(lookback + 1)]
    end = series[-(skip + 1)]
    if not start:
        return None
    return round(end / start - 1, 6)


_TRADING_DAYS = 252


# ---- factors ----

@factor("return_1m")
def _return_1m(ctx: FactorContext) -> float | None:
    return _cum_return(ctx.closes, 21)


@factor("return_3m")
def _return_3m(ctx: FactorContext) -> float | None:
    return _cum_return(ctx.closes, 63)


@factor("return_6m")
def _return_6m(ctx: FactorContext) -> float | None:
    return _cum_return(ctx.closes, 126)


@factor("momentum_12_1")
def _momentum_12_1(ctx: FactorContext) -> float | None:
    # 12-month return skipping the most recent month (classic 12-1 momentum).
    if len(ctx.closes) < 253:
        return None
    start, end = ctx.closes[-253], ctx.closes[-22]
    return round(end / start - 1, 6) if start else None


@factor("residual_momentum_6m")
def _residual_momentum_6m(ctx: FactorContext) -> float | None:
    # 6-month return with the market component removed: r_sym − beta · r_bench.
    sym = _cum_return(ctx.closes, 126)
    if sym is None or not ctx.benchmark_closes:
        return None
    bench = _cum_return(ctx.benchmark_closes, 126)
    beta = _beta_60d(ctx)
    if bench is None or beta is None:
        return None
    return round(sym - beta * bench, 6)


@factor("high_52w_proximity")
def _high_52w_proximity(ctx: FactorContext) -> float | None:
    window = ctx.highs[-_TRADING_DAYS:]
    if len(window) < 20 or not ctx.closes:
        return None
    high = max(window)
    return round(ctx.closes[-1] / high, 6) if high else None


@factor("short_term_reversal_5d")
def _short_term_reversal_5d(ctx: FactorContext) -> float | None:
    r = _cum_return(ctx.closes, 5)
    return round(-r, 6) if r is not None else None  # positive => recent dip (reversal candidate)


@factor("short_term_reversal_20d")
def _short_term_reversal_20d(ctx: FactorContext) -> float | None:
    r = _cum_return(ctx.closes, 20)
    return round(-r, 6) if r is not None else None


@factor("realized_vol_20d")
def _realized_vol_20d(ctx: FactorContext) -> float | None:
    rets = _returns(ctx.closes)
    if len(rets) < 20:
        return None
    s = _std(rets[-20:])
    return round(s * (_TRADING_DAYS ** 0.5), 6) if s is not None else None


@factor("realized_vol_60d")
def _realized_vol_60d(ctx: FactorContext) -> float | None:
    rets = _returns(ctx.closes)
    if len(rets) < 60:
        return None
    s = _std(rets[-60:])
    return round(s * (_TRADING_DAYS ** 0.5), 6) if s is not None else None


@factor("beta_60d")
def _beta_60d(ctx: FactorContext) -> float | None:
    if not ctx.benchmark_closes:
        return None
    sym = _returns(ctx.closes)[-60:]
    bench = _returns(ctx.benchmark_closes)[-60:]
    n = min(len(sym), len(bench))
    if n < 20:
        return None
    cov = _cov(sym[-n:], bench[-n:])
    var = _cov(bench[-n:], bench[-n:])
    if cov is None or not var:
        return None
    return round(cov / var, 6)


@factor("dollar_volume_20d")
def _dollar_volume_20d(ctx: FactorContext) -> float | None:
    if len(ctx.closes) < 1 or len(ctx.volumes) < 1:
        return None
    n = min(20, len(ctx.closes), len(ctx.volumes))
    dvs = [ctx.closes[-i] * ctx.volumes[-i] for i in range(1, n + 1)]
    return round(_mean(dvs), 2) if dvs else None


@factor("amihud_20d")
def _amihud_20d(ctx: FactorContext) -> float | None:
    # Illiquidity: mean(|daily return| / dollar volume), scaled by 1e9 for readability.
    n = min(20, len(ctx.closes) - 1, len(ctx.volumes) - 1)
    if n < 5:
        return None
    vals: list[float] = []
    for i in range(1, n + 1):
        prev, cur, vol = ctx.closes[-i - 1], ctx.closes[-i], ctx.volumes[-i]
        dv = cur * vol
        if prev and dv:
            vals.append(abs(cur / prev - 1) / dv)
    return round(_mean(vals) * 1e9, 6) if vals else None


@factor("volume_shock")
def _volume_shock(ctx: FactorContext) -> float | None:
    if len(ctx.volumes) < 21:
        return None
    base = _mean(ctx.volumes[-21:-1])
    return round(ctx.volumes[-1] / base, 6) if base else None


def compute_factors(ctx: FactorContext) -> dict[str, Any]:
    """Run every registered factor over `ctx`. Missing-data factors are `None` (coverage drops,
    nothing raises). Returns {factor_name: value|None}."""
    return {name: fn(ctx) for name, fn in FACTORS.items()}
