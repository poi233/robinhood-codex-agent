from __future__ import annotations

import json
import subprocess
from pathlib import Path

from trading_agent.core.io import read_json
from trading_agent.strategy.manifest import _git_commit, build_run_manifest


def _make_agent_root(tmp_path: Path) -> Path:
    config_dir = tmp_path / "src" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "universe.txt").write_text("NVDA\nAVGO\nPLTR\n", encoding="utf-8")
    (config_dir / "scoring_profiles.yaml").write_text(
        "default_profile: aggressive_growth\n"
        "profiles:\n"
        "  aggressive_growth:\n"
        "    watchlist_threshold: 35\n"
        "    trade_threshold: 50\n"
        "    high_conviction_threshold: 80\n"
        "    min_effective_coverage: 0.5\n"
        "  conservative:\n"
        "    watchlist_threshold: 45\n"
        "    trade_threshold: 70\n"
        "    high_conviction_threshold: 85\n"
        "    min_effective_coverage: 0.6\n",
        encoding="utf-8",
    )
    return tmp_path


def test_build_run_manifest_writes_expected_fields(tmp_path: Path) -> None:
    agent_root = _make_agent_root(tmp_path)

    manifest = build_run_manifest(agent_root, "2026-06-15")

    assert manifest["run_date"] == "2026-06-15"
    assert manifest["strategy_id"] == "baseline_v1"
    assert manifest["trading_mode"] == "paper"
    assert manifest["effective_risk_tier"] == 4
    assert manifest["scoring_profile"] == "aggressive_growth"
    assert manifest["policy_profile"] == "aggressive_growth"
    assert manifest["active_watchlist_count"] == 3
    assert manifest["codex_model"] == "gpt-5.4"
    assert manifest["codex_model_mini"] == "gpt-5.4-mini"
    assert isinstance(manifest["git_commit"], str) and manifest["git_commit"]
    assert isinstance(manifest["config_hash"], str) and len(manifest["config_hash"]) == 12


def test_build_run_manifest_writes_to_run_state_dir(tmp_path: Path) -> None:
    agent_root = _make_agent_root(tmp_path)

    build_run_manifest(agent_root, "2026-06-15")

    manifest_path = agent_root / "runtime" / "state" / "runs" / "2026-06-15" / "run_manifest.json"
    assert manifest_path.exists()
    on_disk = read_json(manifest_path)
    assert on_disk["run_date"] == "2026-06-15"


def test_config_hash_changes_when_active_strategy_changes(tmp_path: Path, monkeypatch) -> None:
    agent_root = _make_agent_root(tmp_path)
    manifest_a = build_run_manifest(agent_root, "2026-06-15")

    (agent_root / "src" / "config" / "strategy_registry.yaml").write_text(
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
    # apply_active_strategy_env_defaults only fills unset keys, so the first
    # build_run_manifest call already pinned these into os.environ; clear them
    # to observe the new registry entry the way a fresh process would.
    for key in ("SCORING_PROFILE", "POLICY_PROFILE", "RISK_TIER", "PAPER_RISK_TIER"):
        monkeypatch.delenv(key, raising=False)
    manifest_b = build_run_manifest(agent_root, "2026-06-15")

    assert manifest_a["config_hash"] != manifest_b["config_hash"]
    assert manifest_b["strategy_id"] == "experimental_v2"
    assert manifest_b["scoring_profile"] == "conservative"


def test_git_commit_matches_real_repo_head() -> None:
    repo_root = Path(".")
    expected = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    assert _git_commit(repo_root) == expected


def test_git_commit_falls_back_to_unknown_outside_a_git_repo(tmp_path: Path) -> None:
    agent_root = _make_agent_root(tmp_path)

    manifest = build_run_manifest(agent_root, "2026-06-15")

    assert manifest["git_commit"] == "unknown"
