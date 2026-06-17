from __future__ import annotations

from trading_agent.analyzers.ai_signal_schema import (
    make_envelope,
    normalize_catalyst_signal,
    normalize_dsa_signal,
    normalize_kronos_signal,
    validate_ai_signal,
)


def _valid_env(**overrides):
    base = dict(
        layer="kronos", symbol="NVDA", asof_date="2026-06-17", direction="long",
        confidence=0.7, time_horizon="intraday", reason_codes=[], warning_codes=[], risk_flags=[],
    )
    base.update(overrides)
    return make_envelope(**base)


def test_validator_accepts_a_well_formed_envelope():
    assert validate_ai_signal(_valid_env()) == []


def test_validator_flags_missing_asof_and_bad_ranges():
    assert "missing_or_invalid_asof_date" in validate_ai_signal(_valid_env(asof_date="06/17/2026"))
    assert "invalid_confidence" in validate_ai_signal(_valid_env(confidence=1.5))
    assert "invalid_direction" in validate_ai_signal(_valid_env(direction="up"))
    assert "invalid_time_horizon" in validate_ai_signal(_valid_env(time_horizon="forever"))


def test_kronos_normalizer_maps_direction_and_keeps_metrics():
    env = normalize_kronos_signal("nvda", {
        "direction_bias": "bullish", "confidence": 0.72, "setup_bias": "breakout",
        "path_summary": "up_then_consolidate", "risk_flags": ["high_forecast_volatility"],
        "predicted_return_bps": 180, "predicted_volatility_bps": 220,
    }, asof_date="2026-06-17")
    assert validate_ai_signal(env) == []
    assert env["symbol"] == "NVDA"
    assert env["direction"] == "long"
    assert env["confidence"] == 0.72
    assert "setup:breakout" in env["reason_codes"]
    assert env["risk_flags"] == ["high_forecast_volatility"]
    assert env["metrics"]["predicted_return_bps"] == 180


def test_kronos_bearish_maps_to_short():
    env = normalize_kronos_signal("AMD", {"direction_bias": "bearish", "confidence": 0.6}, asof_date="2026-06-17")
    assert env["direction"] == "short"


def test_dsa_normalizer_categorical_confidence_and_codes():
    env = normalize_dsa_signal("SMH", {
        "bias": "candidate", "confidence": "high", "strategy_matches": ["hot_theme", "bull_trend"],
        "setup": "theme_leader", "reject_reasons": ["unverified_catalyst"], "crowding_risk": "high",
        "suggested_premarket_use": "promote", "risk_flags": ["wide_spread"],
    }, asof_date="2026-06-17")
    assert validate_ai_signal(env) == []
    assert env["direction"] == "long"
    assert env["confidence"] == 0.8  # "high" -> 0.8
    assert "hot_theme" in env["reason_codes"] and "setup:theme_leader" in env["reason_codes"]
    assert "unverified_catalyst" in env["warning_codes"]
    assert "crowding_risk:high" in env["warning_codes"]


def test_dsa_block_is_neutral_not_short():
    env = normalize_dsa_signal("XYZ", {"bias": "blocked", "suggested_premarket_use": "block", "confidence": "low"}, asof_date="2026-06-17")
    assert env["direction"] == "neutral"
    assert env["confidence"] == 0.3


def test_catalyst_normalizer_confidence_from_data_quality_and_earnings_warning():
    env = normalize_catalyst_signal("NVDA", {
        "catalysts": ["product launch"], "risk_flags": [], "earnings_risk": "near", "data_quality": "ok",
    }, asof_date="2026-06-17")
    assert validate_ai_signal(env) == []
    assert env["direction"] == "neutral"
    assert env["confidence"] == 0.6  # ok -> 0.6
    assert env["reason_codes"] == ["has_catalyst"]
    assert "earnings_risk_near" in env["warning_codes"]


def test_confidence_uncoercible_defaults_to_zero_but_valid():
    env = normalize_dsa_signal("ABC", {"confidence": "weird", "suggested_premarket_use": "promote"}, asof_date="2026-06-17")
    assert env["confidence"] == 0.0
    assert validate_ai_signal(env) == []  # 0.0 is a valid confidence
