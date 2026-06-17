from __future__ import annotations

from trading_agent.features.factors_price import (
    FACTORS,
    FactorContext,
    compute_factors,
    factor,
)


def _ctx(n: int = 300, *, start: float = 100.0, drift: float = 0.001, vol_last: float | None = None):
    closes = [round(start * (1 + drift) ** i, 4) for i in range(n)]
    highs = [c * 1.01 for c in closes]
    lows = [c * 0.99 for c in closes]
    volumes = [1_000_000.0] * n
    if vol_last is not None:
        volumes[-1] = vol_last
    bench = [round(50.0 * (1 + drift / 2) ** i, 4) for i in range(n)]
    return FactorContext(closes=closes, highs=highs, lows=lows, volumes=volumes, benchmark_closes=bench)


def test_registry_has_expected_factors():
    for name in ("momentum_12_1", "residual_momentum_6m", "high_52w_proximity",
                 "short_term_reversal_5d", "realized_vol_20d", "beta_60d", "amihud_20d",
                 "dollar_volume_20d", "volume_shock"):
        assert name in FACTORS


def test_compute_factors_returns_all_keys_numeric_on_full_history():
    out = compute_factors(_ctx(300))
    assert set(out) == set(FACTORS)
    # uptrending series: 12-1 momentum and 6m return are positive; high proximity near 1.
    assert out["momentum_12_1"] > 0
    assert out["return_6m"] > 0
    assert 0.9 <= out["high_52w_proximity"] <= 1.0
    assert out["realized_vol_20d"] is not None and out["beta_60d"] is not None


def test_insufficient_history_yields_none_not_crash():
    out = compute_factors(_ctx(10))  # far too short for 12-1 / 6m
    assert out["momentum_12_1"] is None
    assert out["return_6m"] is None
    assert out["realized_vol_60d"] is None
    # short windows still computable
    assert out["short_term_reversal_5d"] is not None


def test_volume_shock_detects_spike():
    out = compute_factors(_ctx(60, vol_last=5_000_000.0))
    assert out["volume_shock"] > 4.0  # last day 5x the prior 20d average


def test_residual_momentum_none_without_benchmark():
    ctx = _ctx(200)
    ctx.benchmark_closes = None
    out = compute_factors(ctx)
    assert out["residual_momentum_6m"] is None
    assert out["beta_60d"] is None


def test_registry_is_extensible_register_one_function():
    before = set(FACTORS)
    try:
        @factor("__test_dummy__")
        def _dummy(ctx: FactorContext) -> float:
            return 42.0
        assert compute_factors(_ctx(60))["__test_dummy__"] == 42.0
    finally:
        FACTORS.pop("__test_dummy__", None)
    assert set(FACTORS) == before
