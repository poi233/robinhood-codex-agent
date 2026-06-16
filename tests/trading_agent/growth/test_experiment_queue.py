from pathlib import Path

import pytest

from trading_agent.growth.experiment_queue import (
    ExperimentTransitionError,
    add_experiment,
    approve_experiment,
    archive_experiment,
    list_experiments,
    load_experiments,
    reject_experiment,
)


def _seed_registry(agent_root: Path) -> Path:
    config_dir = agent_root / "src" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    registry = config_dir / "strategy_registry.yaml"
    registry.write_text(
        "active_strategy: baseline_v1\n"
        "strategies:\n"
        "  baseline_v1:\n"
        "    status: active\n",
        encoding="utf-8",
    )
    return registry


def _proposal() -> dict:
    return {
        "proposal_id": "2026-06-16_scoring_trade_threshold",
        "mutation": {"module": "scoring", "field": "trade_threshold", "current": 50.0, "proposed": 40.0},
    }


def test_load_experiments_empty_when_no_file(tmp_path):
    assert load_experiments(tmp_path) == {}


def test_add_experiment_creates_proposed_entry(tmp_path):
    exp = add_experiment(tmp_path, _proposal(), parent_strategy_id="baseline_v1", created_at="2026-06-16")
    assert exp["status"] == "proposed"
    assert exp["parent_strategy_id"] == "baseline_v1"
    assert exp["field"] == "trade_threshold"
    reloaded = load_experiments(tmp_path)
    assert exp["experiment_id"] in reloaded
    assert reloaded[exp["experiment_id"]]["proposed"] == 40.0


def test_list_experiments_filters_by_status(tmp_path):
    add_experiment(tmp_path, _proposal(), parent_strategy_id="baseline_v1", created_at="2026-06-16")
    assert len(list_experiments(tmp_path)) == 1
    assert len(list_experiments(tmp_path, status="proposed")) == 1
    assert len(list_experiments(tmp_path, status="active_shadow")) == 0


def test_approve_moves_to_active_shadow_and_does_not_touch_active_strategy(tmp_path):
    registry = _seed_registry(tmp_path)
    registry_before = registry.read_text(encoding="utf-8")
    exp = add_experiment(tmp_path, _proposal(), parent_strategy_id="baseline_v1", created_at="2026-06-16")

    updated = approve_experiment(tmp_path, exp["experiment_id"])

    assert updated["status"] == "active_shadow"
    assert load_experiments(tmp_path)[exp["experiment_id"]]["status"] == "active_shadow"
    # The hard rule: approving an experiment never switches the champion.
    assert registry.read_text(encoding="utf-8") == registry_before


def test_archive_from_any_state(tmp_path):
    exp = add_experiment(tmp_path, _proposal(), parent_strategy_id="baseline_v1", created_at="2026-06-16")
    approve_experiment(tmp_path, exp["experiment_id"])
    archived = archive_experiment(tmp_path, exp["experiment_id"])
    assert archived["status"] == "archived"


def test_reject_from_proposed(tmp_path):
    exp = add_experiment(tmp_path, _proposal(), parent_strategy_id="baseline_v1", created_at="2026-06-16")
    rejected = reject_experiment(tmp_path, exp["experiment_id"])
    assert rejected["status"] == "rejected"


def test_cannot_approve_archived_experiment(tmp_path):
    exp = add_experiment(tmp_path, _proposal(), parent_strategy_id="baseline_v1", created_at="2026-06-16")
    archive_experiment(tmp_path, exp["experiment_id"])
    with pytest.raises(ExperimentTransitionError):
        approve_experiment(tmp_path, exp["experiment_id"])


def test_approve_unknown_experiment_raises(tmp_path):
    with pytest.raises(KeyError):
        approve_experiment(tmp_path, "nope")
