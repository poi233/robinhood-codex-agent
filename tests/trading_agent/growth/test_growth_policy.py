import json
from pathlib import Path

from trading_agent.growth.policy import DEFAULT_GROWTH_POLICY, load_growth_policy


def test_load_growth_policy_reads_repo_config():
    policy = load_growth_policy(Path.cwd())
    assert policy["mode"] == "paper_only"
    assert "TRADING_MODE" in policy["forbidden_mutations"]
    assert policy["allowed_mutations"]["scoring"]["trade_threshold"]["max_delta"] == 10
    assert policy["allowed_mutations"]["overlay"]["factor_weight"]["max_delta"] == 0.05


def test_missing_file_falls_back_to_safe_defaults(tmp_path):
    policy = load_growth_policy(tmp_path)
    assert policy["enabled"] is False
    assert "place_equity_order" in policy["forbidden_mutations"]


def test_forbidden_list_can_only_widen(tmp_path):
    config_dir = tmp_path / "src" / "config"
    config_dir.mkdir(parents=True)
    # A tampered config that tries to DROP the forbidden list entirely.
    (config_dir / "growth_policy.json").write_text(
        json.dumps({"mode": "paper_only", "forbidden_mutations": ["foo"]}),
        encoding="utf-8",
    )
    policy = load_growth_policy(tmp_path)
    # Hard defaults are always unioned back in; "foo" is added, KILL_SWITCH not removed.
    assert "KILL_SWITCH" in policy["forbidden_mutations"]
    assert "foo" in policy["forbidden_mutations"]
