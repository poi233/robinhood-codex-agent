from __future__ import annotations

from trading_agent.analytics.weight_suggestion import suggest_weights


_CURRENT = {"dsa": 0.25, "technical": 0.30, "kronos": 0.15, "quote": 0.10, "catalyst": 0.20}


def test_suggestion_tilts_toward_higher_ic_and_sums_to_one():
    calibration = {"attribution": {"1": [
        {"component": "technical", "ic": 0.25},   # strong predictor -> should gain weight
        {"component": "dsa", "ic": 0.0},
        {"component": "kronos", "ic": -0.10},      # negative -> should lose weight
        {"component": "quote", "ic": 0.02},
        {"component": "catalyst", "ic": 0.05},
    ]}}
    result = suggest_weights(calibration, _CURRENT, horizon="1")
    assert result["status"] == "ok"
    assert abs(sum(result["suggested_weights"].values()) - 1.0) < 1e-6
    # technical (highest IC) gains; kronos (negative IC) loses.
    assert result["suggested_weights"]["technical"] > _CURRENT["technical"]
    assert result["suggested_weights"]["kronos"] < _CURRENT["kronos"]


def test_damping_zero_keeps_weights_unchanged():
    calibration = {"attribution": {"1": [{"component": "technical", "ic": 0.25}, {"component": "dsa", "ic": 0.0}]}}
    result = suggest_weights(calibration, _CURRENT, horizon="1", damping=0.0)
    assert result["suggested_weights"] == {k: round(v, 4) for k, v in _CURRENT.items()}


def test_insufficient_data_keeps_current_weights():
    result = suggest_weights({"attribution": {"1": []}}, _CURRENT, horizon="1")
    assert result["status"] == "insufficient_data"
    assert result["suggested_weights"] == _CURRENT


def test_report_carries_disclaimer(tmp_path):
    from trading_agent.analytics.weight_suggestion import build_weight_suggestion_report
    report = build_weight_suggestion_report(tmp_path)  # no calibration_report -> insufficient_data
    assert "never auto-applied" in report["disclaimer"]
    assert report["status"] == "insufficient_data"
