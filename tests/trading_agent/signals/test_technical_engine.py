from __future__ import annotations

import copy

from trading_agent.reporting.trader_watch_levels import build_trader_watch_levels
from trading_agent.signals.technical_engine import apply_llm_assessment, build_technical_signals


def _tf(trend: str, *, rsi: float, hist: float, above: bool, ema_bull: bool = True) -> dict:
    side = "above" if above else "below"
    return {
        "last_close": 100.0,
        "sma": {"20": 96.0, "50": 92.0, "200": 80.0},
        "ema": {"9": 99.0 if ema_bull else 95.0, "21": 97.0},
        "price_vs_sma": {"20": side, "50": side, "200": side},
        "rsi_14": rsi,
        "macd": {"macd": 1.2, "signal": 0.8, "hist": hist},
        "atr_14": 2.0,
        "atr_pct": 2.0,
        "avg_volume_20": 1_000_000.0,
        "range_20d": {"high": 104.0, "low": 90.0},
        "high_recent": 104.0,
        "low_recent": 90.0,
        "dist_from_recent_high_pct": 3.8,
        "volume_surge_ratio": 1.1,
        "swing_highs": [103.0, 104.0],
        "swing_lows": [94.0, 91.0],
        "trend": trend,
        "flags": ["pullback_to_sma20"],
    }


def _bullish_daily() -> dict:
    return {
        "data_quality": "ok",
        "timeframes": {
            "weekly": _tf("up", rsi=60.0, hist=0.3, above=True),
            "daily": _tf("up", rsi=62.0, hist=0.4, above=True),
            "hourly": _tf("up", rsi=58.0, hist=0.2, above=True),
            "intraday_15m": _tf("up", rsi=55.0, hist=0.1, above=True),
        },
        "multi_timeframe": {"alignment": "bullish", "rel_strength_vs_spy": {"5d": 2.0, "20d": 3.0, "60d": 4.0}},
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


def test_multi_timeframe_actually_enters_decision() -> None:
    # A symbol bullish on every timeframe must score strictly higher than the same
    # symbol with a bearish higher timeframe — proving weekly/hourly/15m are used.
    all_bull = _bullish_daily()
    mixed = copy.deepcopy(all_bull)
    mixed["timeframes"]["weekly"] = _tf("down", rsi=42.0, hist=-0.3, above=False, ema_bull=False)

    p_all = build_technical_signals(_features({"NVDA": all_bull}), run_date="2026-06-23")["symbols"]["NVDA"]
    p_mixed = build_technical_signals(_features({"NVDA": mixed}), run_date="2026-06-23")["symbols"]["NVDA"]

    assert p_all["priority_score"] > p_mixed["priority_score"]
    assert p_all["engine"]["breakdown"]["per_timeframe"].keys() == {"weekly", "daily", "hourly", "intraday_15m"}


def test_llm_assessment_upgrade_is_bounded() -> None:
    out = build_technical_signals(_features({"NVDA": _bullish_daily()}), run_date="2026-06-23")
    base = out["symbols"]["NVDA"]["priority_score"]
    base_levels = copy.deepcopy(out["symbols"]["NVDA"]["long_setup"])
    out["symbols"]["NVDA"]["llm_assessment"] = {"bias": "bullish", "conviction": 1.0, "chan_signal": "buy"}

    apply_llm_assessment(out, max_swing=12.0)
    sym = out["symbols"]["NVDA"]

    # priority moved up but by no more than the swing bound
    assert base <= sym["priority_score"] <= min(100.0, base + 12.0)
    # price levels / stops are NEVER edited by the LLM
    assert sym["long_setup"] == base_levels


def test_llm_veto_downgrades_to_avoid_and_blocks() -> None:
    out = build_technical_signals(_features({"NVDA": _bullish_daily()}), run_date="2026-06-23")
    out["symbols"]["NVDA"]["llm_assessment"] = {"bias": "bullish", "conviction": 0.9, "veto": True}

    apply_llm_assessment(out)
    sym = out["symbols"]["NVDA"]

    assert sym["technical_action"] == "avoid"
    # veto must block trading via no_trade_zone (caution-only)
    assert sym["no_trade_zone"]["reason"] == "llm_veto"
    assert sym["no_trade_zone"]["high"] > sym["no_trade_zone"]["low"]


def test_llm_missing_or_failed_is_noop() -> None:
    # no llm_assessment → engine baseline unchanged
    out = build_technical_signals(_features({"NVDA": _bullish_daily()}), run_date="2026-06-23")
    before = copy.deepcopy(out["symbols"]["NVDA"])
    apply_llm_assessment(out)
    after = out["symbols"]["NVDA"]
    after.pop("engine")
    before.pop("engine")
    assert after == before

    # failed-data symbol is never resurrected by the LLM
    failed = build_technical_signals(
        _features({"X": {"data_quality": "failed", "timeframes": {}, "multi_timeframe": {}}}),
        run_date="2026-06-23",
    )
    failed["symbols"]["X"]["llm_assessment"] = {"bias": "bullish", "conviction": 1.0}
    apply_llm_assessment(failed)
    assert failed["symbols"]["X"]["technical_action"] == "avoid"
