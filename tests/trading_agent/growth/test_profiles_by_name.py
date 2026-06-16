from pathlib import Path

from trading_agent.planner.scoring_profiles import load_scoring_profile
from trading_agent.policy.profiles import load_policy_profile


def _write_scoring_yaml(config_dir: Path) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "scoring_profiles.yaml").write_text(
        "default_profile: aggressive_growth\n"
        "profiles:\n"
        "  aggressive_growth:\n"
        "    trade_threshold: 50\n"
        "  conservative:\n"
        "    trade_threshold: 70\n",
        encoding="utf-8",
    )


def test_scoring_profile_by_name_ignores_env(tmp_path, monkeypatch):
    _write_scoring_yaml(tmp_path / "config")
    monkeypatch.setenv("SCORING_PROFILE", "aggressive_growth")
    profile = load_scoring_profile(tmp_path / "config", profile_name="conservative")
    assert profile["name"] == "conservative"
    assert profile["trade_threshold"] == 70.0


def test_scoring_profile_default_still_reads_env(tmp_path, monkeypatch):
    _write_scoring_yaml(tmp_path / "config")
    monkeypatch.setenv("SCORING_PROFILE", "conservative")
    profile = load_scoring_profile(tmp_path / "config")
    assert profile["name"] == "conservative"


def test_policy_profile_by_name_ignores_env(tmp_path, monkeypatch):
    config_dir = tmp_path / "src" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "policy_profiles.json").write_text(
        '{"profiles": {"conservative": {"min_reward_risk": 1.75},'
        ' "aggressive_growth": {"min_reward_risk": 1.5}}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("POLICY_PROFILE", "aggressive_growth")
    profile = load_policy_profile(tmp_path, profile_name="conservative")
    assert profile["name"] == "conservative"
    assert profile["min_reward_risk"] == 1.75
