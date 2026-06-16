from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from trading_agent.core.config import load_runtime_config
from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import write_json
from trading_agent.data.universe import parse_active_watchlist
from trading_agent.planner.scoring_profiles import load_scoring_profile
from trading_agent.policy.profiles import load_policy_profile
from trading_agent.strategy.registry import load_active_strategy


def _git_commit(agent_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=agent_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    if result.returncode != 0:
        return "unknown"
    return result.stdout.strip()


def _config_hash(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:12]


def _active_watchlist_count(config_dir: Path) -> int:
    try:
        return len(parse_active_watchlist(config_dir))
    except OSError:
        return 0


def build_run_manifest(agent_root: Path, run_date: str) -> dict[str, Any]:
    """Build and write run_manifest.json so any run's result can be traced back
    to the strategy version, config, and model that produced it.

    Called once per lifecycle entrypoint (premarket/intraday/postmarket); each
    call overwrites the same run-date file with the latest resolved config, so
    whichever entrypoint ran most recently for that date reflects current state.
    """
    paths = build_runtime_paths(agent_root, run_date=run_date)
    runtime = load_runtime_config(agent_root)
    strategy = load_active_strategy(agent_root)
    scoring_profile = load_scoring_profile(paths.config_dir)
    policy_profile = load_policy_profile(agent_root)
    active_watchlist_count = _active_watchlist_count(paths.config_dir)

    config_hash = _config_hash(
        {
            "trading_mode": runtime.trading_mode,
            "risk_tier": runtime.risk_tier,
            "paper_risk_tier": runtime.paper_risk_tier,
            "strategy": strategy,
            "scoring_profile": scoring_profile,
            "policy_profile": policy_profile,
        }
    )

    manifest = {
        "run_date": run_date,
        "strategy_id": strategy["strategy_id"],
        "trading_mode": runtime.trading_mode,
        "effective_risk_tier": runtime.effective_risk_tier,
        "scoring_profile": scoring_profile["name"],
        "policy_profile": policy_profile["name"],
        "active_watchlist_count": active_watchlist_count,
        "git_commit": _git_commit(agent_root),
        "config_hash": config_hash,
        "codex_model": runtime.codex_model,
    }
    write_json(paths.run_state_dir / "run_manifest.json", manifest)
    return manifest
