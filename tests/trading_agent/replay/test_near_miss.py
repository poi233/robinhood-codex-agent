from __future__ import annotations

from pathlib import Path

from trading_agent.core.io import write_json
from trading_agent.replay.forward_returns import ForwardReturnRecord
from trading_agent.replay.near_miss import load_trade_thresholds, near_threshold_analysis


def test_load_trade_thresholds_reads_risk_overlay(tmp_path):
    write_json(tmp_path / "runtime" / "state" / "runs" / "2026-06-15" / "planner" / "risk_overlay.json",
               {"trade_score_threshold": 55.0})
    assert load_trade_thresholds(tmp_path, ["2026-06-15"]) == {"2026-06-15": 55.0}


def test_near_threshold_analysis_classifies_and_aggregates():
    # threshold 50, margin 5 => cleared >=50, near_miss [45,50), below <45.
    records = [
        ForwardReturnRecord("d", "A", candidate_score=60.0, trade_readiness_score=None, price_setup_score=None, returns={1: 0.04}),
        ForwardReturnRecord("d", "B", candidate_score=48.0, trade_readiness_score=None, price_setup_score=None, returns={1: 0.05}),  # near miss, big winner
        ForwardReturnRecord("d", "C", candidate_score=46.0, trade_readiness_score=None, price_setup_score=None, returns={1: -0.01}),
        ForwardReturnRecord("d", "D", candidate_score=20.0, trade_readiness_score=None, price_setup_score=None, returns={1: -0.03}),
    ]
    out = near_threshold_analysis(records, {"d": 50.0}, margin=5.0, horizons=(1,))
    h1 = out["1"]
    assert h1["cleared"]["count"] == 1
    assert h1["near_miss"]["count"] == 2     # B and C
    assert h1["below"]["count"] == 1
    # near_miss mean return is positive and >= cleared here => threshold likely too strict signal
    assert h1["near_miss"]["mean_return"] == round((0.05 + -0.01) / 2, 6)
    assert 0.0 <= h1["near_miss"]["hit_rate"] <= 1.0


def test_near_threshold_skips_records_without_score_or_return():
    records = [
        ForwardReturnRecord("d", "A", candidate_score=None, trade_readiness_score=None, price_setup_score=None, returns={1: 0.04}),
        ForwardReturnRecord("d", "B", candidate_score=48.0, trade_readiness_score=None, price_setup_score=None, returns={1: None}),
    ]
    out = near_threshold_analysis(records, {"d": 50.0}, margin=5.0, horizons=(1,))
    assert out["1"]["near_miss"]["count"] == 0
    assert out["1"]["cleared"]["count"] == 0
