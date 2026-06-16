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
    assert profile["max_scored_candidates"] == 20
    assert profile["max_watchlist"] == 8
    assert profile["max_tradable"] == 8


def test_max_candidate_caps_are_configurable(tmp_path) -> None:
    config_dir = tmp_path
    (config_dir / "scoring_profiles.yaml").write_text(
        "default_profile: aggressive_growth\n"
        "max_scored_candidates: 5\n"
        "max_watchlist: 2\n"
        "max_tradable: 1\n"
        "profiles:\n"
        "  aggressive_growth:\n"
        "    watchlist_threshold: 35\n"
        "    trade_threshold: 50\n"
        "    high_conviction_threshold: 80\n"
        "    min_effective_coverage: 0.5\n",
        encoding="utf-8",
    )

    profile = load_scoring_profile(config_dir)

    assert profile["max_scored_candidates"] == 5
    assert profile["max_watchlist"] == 2
    assert profile["max_tradable"] == 1


def test_unknown_scoring_profile_falls_back_to_default(monkeypatch) -> None:
    monkeypatch.setenv("SCORING_PROFILE", "does_not_exist")

    profile = load_scoring_profile(Path("src/config"))

    assert profile["name"] == "aggressive_growth"
    assert profile["trade_threshold"] == 50.0
