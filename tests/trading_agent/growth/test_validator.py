from pathlib import Path

from trading_agent.growth.policy import load_growth_policy
from trading_agent.growth.validator import validate_mutation

POLICY = load_growth_policy(Path.cwd())


def test_forbidden_field_is_rejected():
    ok, violations = validate_mutation(
        {"module": "risk", "field": "per_trade_risk_pct", "current": 0.005, "proposed": 0.02}, POLICY
    )
    assert ok is False
    assert any("forbidden_mutation" in v for v in violations)


def test_out_of_range_is_rejected():
    ok, violations = validate_mutation(
        {"module": "scoring", "field": "trade_threshold", "current": 50, "proposed": 95}, POLICY
    )
    assert ok is False
    assert any("outside" in v for v in violations)


def test_over_delta_is_rejected():
    ok, violations = validate_mutation(
        {"module": "scoring", "field": "trade_threshold", "current": 50, "proposed": 70}, POLICY
    )
    assert ok is False
    assert any("delta" in v for v in violations)


def test_valid_paper_only_mutation_passes():
    ok, violations = validate_mutation(
        {"module": "scoring", "field": "trade_threshold", "current": 50, "proposed": 56}, POLICY
    )
    assert ok is True
    assert violations == []


def test_valid_overlay_mutation_passes():
    ok, violations = validate_mutation(
        {"module": "overlay", "field": "factor_weight", "current": 0.10, "proposed": 0.14}, POLICY
    )
    assert ok is True
    assert violations == []


def test_overlay_mutation_respects_max_delta():
    ok, violations = validate_mutation(
        {"module": "overlay", "field": "regime_size_multiplier", "current": 0.50, "proposed": 0.80}, POLICY
    )
    assert ok is False
    assert any("delta" in v for v in violations)


def test_field_not_in_whitelist_is_rejected():
    ok, violations = validate_mutation(
        {"module": "scoring", "field": "mystery_knob", "current": 1, "proposed": 2}, POLICY
    )
    assert ok is False
    assert any("not_in_whitelist" in v for v in violations)


def test_component_weights_sum_must_stay_normalized():
    ok, violations = validate_mutation(
        {
            "module": "scoring",
            "field": "component_weights",
            "current_weights": {"dsa": 0.25, "technical": 0.30, "kronos": 0.15, "quote": 0.10, "catalyst": 0.20},
            "proposed_weights": {"dsa": 0.50, "technical": 0.30, "kronos": 0.15, "quote": 0.10, "catalyst": 0.20},
        },
        POLICY,
    )
    assert ok is False  # sum 1.25 outside [0.95, 1.05] AND dsa delta 0.25 > 0.10


def test_non_paper_only_policy_is_rejected():
    ok, violations = validate_mutation(
        {"module": "scoring", "field": "trade_threshold", "current": 50, "proposed": 56},
        {**POLICY, "mode": "live"},
    )
    assert ok is False
    assert any("paper_only" in v for v in violations)
