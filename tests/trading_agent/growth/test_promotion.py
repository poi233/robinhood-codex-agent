import json
from pathlib import Path

import pytest

from trading_agent.growth.promotion import build_promotion_check, write_promotion_check


def _seed(agent_root: Path, *, status: str) -> Path:
    config_dir = agent_root / "src" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    registry = config_dir / "strategy_registry.yaml"
    registry.write_text(
        "active_strategy: baseline_v1\nstrategies:\n  baseline_v1:\n    status: active\n", encoding="utf-8")
    (config_dir / "growth_policy.json").write_text(json.dumps({
        "mode": "paper_only",
        "promotion_rules": {"min_shadow_days": 1, "fill_rate_not_worse_than_champion": False,
                            "max_drawdown_not_worse_than_champion": False, "require_human_final_approval": True},
    }), encoding="utf-8")
    (config_dir / "strategy_experiments.yaml").write_text(
        "experiments:\n"
        "  exp_2026-06-15_scoring_trade_threshold:\n"
        f"    status: {status}\n"
        "    challenger_strategy_id: \"baseline_v1__trade_threshold_40\"\n"
        "    parent_strategy_id: baseline_v1\n"
        "    module: scoring\n"
        "    field: trade_threshold\n"
        "    current: 50.0\n"
        "    proposed: 40.0\n",
        encoding="utf-8",
    )
    return registry


def _seed_shadow_day(agent_root: Path) -> None:
    from trading_agent.core.context import build_experiment_paths
    paths = build_experiment_paths(agent_root, run_date="2026-06-15", strategy_id="baseline_v1__trade_threshold_40")
    paths.shadow_decisions_log_path.parent.mkdir(parents=True, exist_ok=True)
    paths.shadow_decisions_log_path.write_text(
        json.dumps({"run_date": "2026-06-15", "decision": "would_trade", "blocked_reasons": []}) + "\n", encoding="utf-8")
    (agent_root / "runtime" / "state" / "runs" / "2026-06-15").mkdir(parents=True, exist_ok=True)


def test_promotion_check_never_modifies_registry(tmp_path):
    registry = _seed(tmp_path, status="ready_for_review")
    _seed_shadow_day(tmp_path)
    before = registry.read_text(encoding="utf-8")

    result = build_promotion_check(tmp_path, "exp_2026-06-15_scoring_trade_threshold")

    assert registry.read_text(encoding="utf-8") == before
    assert result["experiment_id"] == "exp_2026-06-15_scoring_trade_threshold"
    assert "changelog_draft" in result
    assert "registry_entry_draft" in result
    assert "baseline_v1__trade_threshold_40" in result["changelog_draft"]


def test_eligible_only_when_ready_for_review_and_recommended(tmp_path):
    _seed(tmp_path, status="active_shadow")
    _seed_shadow_day(tmp_path)
    result = build_promotion_check(tmp_path, "exp_2026-06-15_scoring_trade_threshold")
    # active_shadow (not ready_for_review) => not eligible even if metrics pass.
    assert result["eligible"] is False
    assert any("not ready_for_review" in r or "ready_for_review" in r for r in result["blocking_reasons"])


def test_ready_and_recommended_is_eligible(tmp_path):
    _seed(tmp_path, status="ready_for_review")
    _seed_shadow_day(tmp_path)
    result = build_promotion_check(tmp_path, "exp_2026-06-15_scoring_trade_threshold")
    assert result["eligible"] is True


def test_unknown_experiment_raises(tmp_path):
    _seed(tmp_path, status="ready_for_review")
    with pytest.raises(KeyError):
        build_promotion_check(tmp_path, "nope")


def test_write_promotion_check_emits_draft_and_leaves_registry_untouched(tmp_path):
    registry = _seed(tmp_path, status="ready_for_review")
    _seed_shadow_day(tmp_path)
    before = registry.read_text(encoding="utf-8")

    out = write_promotion_check(tmp_path, "exp_2026-06-15_scoring_trade_threshold")

    assert out.exists()
    assert "Changelog draft" in out.read_text(encoding="utf-8")
    assert registry.read_text(encoding="utf-8") == before
