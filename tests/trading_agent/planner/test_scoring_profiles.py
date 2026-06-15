from __future__ import annotations

from pathlib import Path

from trading_agent.planner.scoring_profiles import load_scoring_profile


def test_default_scoring_profile_loads() -> None:
    profile = load_scoring_profile(Path("src/config"))

    assert profile["name"] == "aggressive_growth"
    assert profile["watchlist_threshold"] == 35.0
    assert profile["trade_threshold"] == 50.0
    assert profile["high_conviction_threshold"] == 80.0
    assert profile["min_effective_coverage"] == 0.5


def test_unknown_scoring_profile_falls_back_to_default(monkeypatch) -> None:
    monkeypatch.setenv("SCORING_PROFILE", "does_not_exist")

    profile = load_scoring_profile(Path("src/config"))

    assert profile["name"] == "aggressive_growth"
    assert profile["trade_threshold"] == 50.0
