from __future__ import annotations

from pathlib import Path

from trading_agent.strategy.registry import (
    DEFAULT_STRATEGY,
    apply_active_strategy_env_defaults,
    list_strategy_ids,
    load_active_strategy,
)


def test_load_active_strategy_falls_back_to_default_when_registry_missing(tmp_path: Path) -> None:
    strategy = load_active_strategy(tmp_path)

    assert strategy == DEFAULT_STRATEGY


def test_load_active_strategy_reads_repo_registry() -> None:
    strategy = load_active_strategy(Path("."))

    assert strategy["strategy_id"] == "baseline_v1"
    assert strategy["status"] == "active"
    assert strategy["scoring_profile"] == "aggressive_growth"
    assert strategy["policy_profile"] == "aggressive_growth"
    assert strategy["risk_tier_paper"] == 4
    assert strategy["risk_tier_live"] == 3


def test_switching_active_strategy_switches_the_whole_profile_tier_combo(tmp_path: Path) -> None:
    config_dir = tmp_path / "src" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "strategy_registry.yaml").write_text(
        "active_strategy: experimental_v2\n"
        "strategies:\n"
        "  baseline_v1:\n"
        "    status: retired\n"
        "    scoring_profile: aggressive_growth\n"
        "    policy_profile: aggressive_growth\n"
        "    risk_tier_paper: 4\n"
        "    risk_tier_live: 3\n"
        "    change_reason: \"superseded by experimental_v2\"\n"
        "  experimental_v2:\n"
        "    status: active\n"
        "    scoring_profile: conservative\n"
        "    policy_profile: conservative\n"
        "    risk_tier_paper: 2\n"
        "    risk_tier_live: 1\n"
        "    parent: baseline_v1\n"
        "    change_reason: \"tighten thresholds while validating new sizing logic\"\n",
        encoding="utf-8",
    )

    strategy = load_active_strategy(tmp_path)

    assert strategy["strategy_id"] == "experimental_v2"
    assert strategy["scoring_profile"] == "conservative"
    assert strategy["policy_profile"] == "conservative"
    assert strategy["risk_tier_paper"] == 2
    assert strategy["risk_tier_live"] == 1
    assert strategy["parent"] == "baseline_v1"


def test_apply_active_strategy_env_defaults_fills_unset_keys_only(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "src" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "strategy_registry.yaml").write_text(
        "active_strategy: experimental_v2\n"
        "strategies:\n"
        "  experimental_v2:\n"
        "    scoring_profile: conservative\n"
        "    policy_profile: conservative\n"
        "    risk_tier_paper: 2\n"
        "    risk_tier_live: 1\n"
        "    change_reason: \"test\"\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("SCORING_PROFILE", raising=False)
    monkeypatch.delenv("POLICY_PROFILE", raising=False)
    monkeypatch.delenv("RISK_TIER", raising=False)
    monkeypatch.setenv("PAPER_RISK_TIER", "9")

    apply_active_strategy_env_defaults(tmp_path)

    import os

    assert os.environ["SCORING_PROFILE"] == "conservative"
    assert os.environ["POLICY_PROFILE"] == "conservative"
    assert os.environ["RISK_TIER"] == "1"
    assert os.environ["PAPER_RISK_TIER"] == "9"


def test_list_strategy_ids_reads_repo_registry() -> None:
    assert list_strategy_ids(Path(".")) == ["baseline_v1"]


def test_every_registered_strategy_has_a_changelog_entry() -> None:
    """roadmap B4 acceptance: every change_reason in the registry has a matching
    docs/strategy-changelog.md entry, identified by its strategy_id heading."""
    changelog = Path("docs/strategy-changelog.md").read_text(encoding="utf-8")

    for strategy_id in list_strategy_ids(Path(".")):
        assert f"## {strategy_id}" in changelog, f"missing changelog entry for {strategy_id}"
