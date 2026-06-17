from __future__ import annotations

import json
from pathlib import Path

from trading_agent.analyzers.factor_alpha import (
    _percentile_ranks,
    compute_factor_alpha,
    load_factor_profile,
)
from trading_agent.features.factor_store import build_factor_panel, build_factor_alpha_payload


def test_load_repo_factor_profile():
    profile = load_factor_profile(Path.cwd())
    assert profile["name"] == "baseline_price_factors_v1"
    assert profile["enabled"] is True
    assert "residual_momentum_6m" in profile["weights"]


def test_load_factor_profile_by_name_ignores_env(tmp_path, monkeypatch):
    cfg = tmp_path / "src" / "config"
    cfg.mkdir(parents=True)
    (cfg / "factor_profiles.json").write_text(json.dumps({
        "default_profile": "a",
        "profiles": {"a": {"weights": {"momentum_12_1": 0.5}}, "b": {"weights": {"return_1m": 0.5}}},
    }), encoding="utf-8")
    monkeypatch.setenv("FACTOR_PROFILE", "a")
    p = load_factor_profile(tmp_path, profile_name="b")
    assert p["name"] == "b" and "return_1m" in p["weights"]


def test_percentile_ranks_ties_and_extremes():
    ranks = _percentile_ranks({"a": 1.0, "b": 2.0, "c": 3.0})
    assert ranks["a"] == 0.0 and ranks["c"] == 100.0 and ranks["b"] == 50.0
    tied = _percentile_ranks({"x": 5.0, "y": 5.0})
    assert tied["x"] == tied["y"]  # ties share rank


def test_compute_factor_alpha_positive_and_negative_weights():
    # 3 symbols. momentum higher-better (+), realized_vol lower-better (-).
    panel = {
        "A": {"momentum_12_1": 0.30, "realized_vol_20d": 0.20},  # high momentum, low vol -> best
        "B": {"momentum_12_1": 0.10, "realized_vol_20d": 0.50},  # low momentum, high vol -> worst
        "C": {"momentum_12_1": 0.20, "realized_vol_20d": 0.35},  # middle
    }
    profile = {"weights": {"momentum_12_1": 0.5, "realized_vol_20d": -0.5}, "risk_filters": {}}
    out = compute_factor_alpha(panel, profile)
    assert out["A"]["factor_alpha_score"] > out["C"]["factor_alpha_score"] > out["B"]["factor_alpha_score"]
    # negative-weight factor: A (lowest vol) gets the high rank after inversion
    assert out["A"]["factor_components"]["realized_vol_20d"] == 100.0
    assert out["B"]["factor_components"]["realized_vol_20d"] == 0.0


def test_compute_factor_alpha_coverage_when_factor_missing():
    panel = {"A": {"momentum_12_1": 0.3}, "B": {"momentum_12_1": 0.1, "high_52w_proximity": 0.9}}
    profile = {"weights": {"momentum_12_1": 0.5, "high_52w_proximity": 0.5}, "risk_filters": {}}
    out = compute_factor_alpha(panel, profile)
    assert out["A"]["coverage"] == 0.5   # only 1 of 2 weighted factors available
    assert out["B"]["coverage"] == 1.0
    assert out["A"]["factor_alpha_score"] is not None


def test_risk_flags_from_filters():
    panel = {"A": {"beta_60d": 3.0, "dollar_volume_20d": 1000.0, "realized_vol_20d": 0.9, "momentum_12_1": 0.2}}
    profile = {"weights": {"momentum_12_1": 1.0},
               "risk_filters": {"max_beta_60d": 2.5, "min_dollar_volume_20d": 50000000, "max_realized_vol_20d": 0.8}}
    out = compute_factor_alpha(panel, profile)
    assert set(out["A"]["risk_flags"]) == {"high_beta", "low_liquidity", "high_volatility"}


def test_build_factor_panel_and_payload_from_bars():
    bars = [{"close": 100 + i, "high": 101 + i, "low": 99 + i, "volume": 1_000_000} for i in range(300)]
    bench = [{"close": 50 + i * 0.5, "high": 50, "low": 50, "volume": 1} for i in range(300)]
    panel = build_factor_panel({"NVDA": bars}, bench)
    assert "NVDA" in panel
    assert panel["NVDA"]["data_quality"] in {"ok", "partial"}
    assert "momentum_12_1" in panel["NVDA"]
    payload = build_factor_alpha_payload(
        compute_factor_alpha(panel, load_factor_profile(Path.cwd())), run_date="2026-06-15", profile_name="baseline_price_factors_v1")
    assert payload["profile"] == "baseline_price_factors_v1"
    assert "NVDA" in payload["symbols"]
