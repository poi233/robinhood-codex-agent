from __future__ import annotations

from trading_agent.screener.config import load_screener_config
from trading_agent.screener.factor_gate import (
    compute_factor_score,
    evaluate_candidate,
    validate_candidates,
)


def _series(n: int, *, start: float, drift: float, volume: float) -> list[dict[str, float]]:
    rows = []
    price = start
    for i in range(n):
        price = max(1.0, price + drift)
        rows.append(
            {
                "date": f"2026-01-{(i % 27) + 1:02d}T{i:04d}",
                "open": price - 0.1,
                "high": price + 0.2,
                "low": price - 0.2,
                "close": price,
                "volume": volume,
            }
        )
    # stable, strictly increasing date strings so sort is deterministic
    for i, row in enumerate(rows):
        row["date"] = f"2026{i:05d}"
    return rows


CONFIG = load_screener_config(env={})  # defaults: min_dollar_vol 20M, require_uptrend True


def test_compute_factor_score_rewards_strength_and_uptrend():
    strong = compute_factor_score(rel_strength_20d=8.0, ret_60d=20.0, above_sma50=True, above_sma200=True)
    weak = compute_factor_score(rel_strength_20d=-5.0, ret_60d=-10.0, above_sma50=False, above_sma200=False)
    assert strong > weak
    # trend terms alone separate two otherwise-flat names
    assert compute_factor_score(rel_strength_20d=0.0, ret_60d=0.0, above_sma50=True, above_sma200=True) > 0
    assert compute_factor_score(rel_strength_20d=0.0, ret_60d=0.0, above_sma50=False, above_sma200=False) < 0


def test_strong_liquid_uptrend_passes():
    rows = _series(260, start=100.0, drift=0.5, volume=5_000_000)  # ~$650M+ dollar vol
    bench = [float(r["close"]) for r in _series(260, start=400.0, drift=0.05, volume=1)]
    ev = evaluate_candidate("UP", rows, bench, CONFIG)
    assert ev.passed_gate is True
    assert ev.reject_reason is None
    assert ev.above_sma200 is True
    assert ev.factor_score is not None


def test_downtrend_fails_uptrend_gate():
    rows = _series(260, start=300.0, drift=-0.5, volume=5_000_000)
    ev = evaluate_candidate("DOWN", rows, None, CONFIG)
    assert ev.passed_gate is False
    assert ev.reject_reason == "not_in_uptrend"


def test_thin_liquidity_fails_volume_gate():
    rows = _series(260, start=10.0, drift=0.2, volume=1_000)  # ~$2k dollar vol << 20M
    ev = evaluate_candidate("THIN", rows, None, CONFIG)
    assert ev.passed_gate is False
    assert ev.reject_reason == "below_min_dollar_volume"


def test_short_history_fails_data_gate():
    rows = _series(30, start=50.0, drift=0.4, volume=5_000_000)
    ev = evaluate_candidate("SHORT", rows, None, CONFIG)
    assert ev.passed_gate is False
    assert ev.reject_reason == "insufficient_data"
    assert ev.data_quality != "ok"


def test_empty_rows_is_no_data():
    ev = evaluate_candidate("NONE", None, None, CONFIG)
    assert ev.passed_gate is False
    assert ev.reject_reason == "no_data"
    assert ev.factor_score is None


def test_loose_config_allows_downtrend_if_liquid():
    loose = load_screener_config(env={"SCREEN_REQUIRE_UPTREND": "0"})
    rows = _series(260, start=300.0, drift=-0.5, volume=5_000_000)
    ev = evaluate_candidate("DOWN", rows, None, loose)
    assert ev.passed_gate is True  # liquidity + data ok, trend gate disabled


def test_validate_candidates_orchestrates_and_fails_closed_on_download_error():
    def good_downloader(tickers, lookback_days, run_date):
        out = {}
        for t in tickers:
            if t == "SPY":
                out[t] = _series(260, start=400.0, drift=0.05, volume=1)
            elif t == "UP":
                out[t] = _series(260, start=100.0, drift=0.6, volume=5_000_000)
            elif t == "DOWN":
                out[t] = _series(260, start=300.0, drift=-0.5, volume=5_000_000)
        return out

    results = validate_candidates(["UP", "DOWN", "up"], config=CONFIG, run_date="2026-06-21", downloader=good_downloader)
    by_symbol = {r.symbol: r for r in results}
    assert set(by_symbol) == {"UP", "DOWN"}  # deduped, upper-cased
    assert by_symbol["UP"].passed_gate is True
    assert by_symbol["DOWN"].passed_gate is False

    def boom(tickers, lookback_days, run_date):
        raise RuntimeError("network down")

    failed = validate_candidates(["UP"], config=CONFIG, run_date="2026-06-21", downloader=boom)
    assert failed[0].reject_reason == "no_data"  # fail-closed, no raise
