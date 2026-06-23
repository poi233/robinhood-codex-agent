from __future__ import annotations

from trading_agent.reporting.trader_watch_levels import build_trader_watch_levels
from trading_agent.signals.technical_engine import build_technical_signals


def _bullish_daily() -> dict:
    return {
        "data_quality": "ok",
        "timeframes": {
            "daily": {
                "last_close": 100.0,
                "sma": {"20": 96.0, "50": 92.0, "200": 80.0},
                "price_vs_sma": {"20": "above", "50": "above", "200": "above"},
                "rsi_14": 62.0,
                "macd": {"macd": 1.2, "signal": 0.8, "hist": 0.4},
                "atr_14": 2.0,
                "range_20d": {"high": 104.0, "low": 90.0},
                "high_recent": 104.0,
                "low_recent": 90.0,
                "dist_from_recent_high_pct": 3.8,
                "volume_surge_ratio": 1.1,
                "swing_highs": [103.0, 104.0],
                "swing_lows": [94.0, 91.0],
                "trend": "up",
                "flags": ["pullback_to_sma20"],
            }
        },
        "multi_timeframe": {"alignment": "bullish", "rel_strength_vs_spy": {"20d": 3.0}},
    }


def _features(symbols: dict) -> dict:
    return {"date": "2026-06-23", "symbols": symbols}


def test_bullish_symbol_gets_buy_action_and_valid_setup() -> None:
    out = build_technical_signals(_features({"NVDA": _bullish_daily()}), run_date="2026-06-23")
    sym = out["symbols"]["NVDA"]

    assert sym["technical_action"] in {"buy_bias", "promote", "strong_promote"}
    assert sym["priority_score"] >= 70
    assert sym["long_setup"]["status"] == "valid"
    assert sym["long_setup"]["setup_type"] in {"pullback", "breakout"}
    # decision-critical levels are concrete numbers
    assert sym["key_levels"]["reference_price"] == 100.0
    assert sym["long_setup"]["trigger_above"] > 0
    assert sym["long_setup"]["invalidation_below"] > 0
    # bullish setups must not self-block via no_trade_zone
    assert sym["no_trade_zone"]["low"] == 0.0 and sym["no_trade_zone"]["high"] == 0.0


def test_failed_data_quality_is_fail_closed() -> None:
    feats = {"WXYZ": {"data_quality": "failed", "timeframes": {}, "multi_timeframe": {}}}
    out = build_technical_signals(_features(feats), run_date="2026-06-23")
    sym = out["symbols"]["WXYZ"]

    assert sym["technical_action"] == "avoid"
    assert sym["confidence"] == 0.0
    assert sym["long_setup"]["status"] == "invalid"


def test_chasing_guard_downgrades_overbought_to_observe() -> None:
    daily = _bullish_daily()
    daily["timeframes"]["daily"]["rsi_14"] = 82.0  # overbought → chase guard
    out = build_technical_signals(_features({"NVDA": daily}), run_date="2026-06-23")
    sym = out["symbols"]["NVDA"]

    assert sym["technical_action"] == "observe"
    assert "chase_guard" in sym["decision_rationale"]


def test_output_is_consumable_by_trader_watch_levels() -> None:
    out = build_technical_signals(_features({"NVDA": _bullish_daily()}), run_date="2026-06-23")
    watch = build_trader_watch_levels(out)
    levels = watch["symbols"]["NVDA"]

    # the price gate reads these keys; they must be populated and numeric
    for key in ("reference_price", "buy_trigger_above", "entry_low", "entry_high", "invalidation_below", "target_1"):
        assert isinstance(levels[key], (int, float))


def test_short_setup_status_arms_sell_risk_exit() -> None:
    # policy/sell.evaluate_sell only arms risk_exit when short_setup.status is in
    # {"active", "watch"}; a mismatch silently disables the risk-reduction exit.
    out = build_technical_signals(_features({"NVDA": _bullish_daily()}), run_date="2026-06-23")
    sym = out["symbols"]["NVDA"]
    assert sym["short_setup"]["status"] in {"active", "watch"}
    assert sym["short_setup"]["trigger_below"] > 0


def test_deterministic_repeatable() -> None:
    feats = _features({"NVDA": _bullish_daily()})
    a = build_technical_signals(feats, run_date="2026-06-23")["symbols"]["NVDA"]
    b = build_technical_signals(feats, run_date="2026-06-23")["symbols"]["NVDA"]
    a.pop("engine"), b.pop("engine")  # identical
    assert a == b
