from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from trading_agent.core.time import pt_date_string


@dataclass(frozen=True)
class RuntimePaths:
    agent_root: Path
    config_dir: Path
    scripts_dir: Path
    state_dir: Path
    logs_dir: Path
    reports_dir: Path
    run_date: str
    run_state_dir: Path
    run_logs_dir: Path
    signals_dir: Path
    planner_dir: Path
    archive_dir: Path
    market_feed_dir: Path
    dsa_signals_path: Path
    kronos_signals_path: Path
    technical_signals_path: Path
    daily_plan_path: Path
    daily_plan_markdown_path: Path
    dynamic_allowlist_path: Path
    today_allowlist_path: Path
    daily_usage_path: Path
    decisions_log_path: Path
    orders_log_path: Path
    codex_run_log_path: Path
    error_log_path: Path
    postmarket_summary_path: Path


def _resolve_env_path(agent_root: Path, env_name: str, default: Path) -> Path:
    raw = os.environ.get(env_name)
    if not raw:
        return default
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate
    return agent_root / candidate


def build_runtime_paths(agent_root: Path, *, run_date: str | None = None) -> RuntimePaths:
    resolved_run_date = run_date or os.environ.get("RUN_DATE_PT") or pt_date_string()
    state_dir = agent_root / "state"
    logs_dir = agent_root / "logs"
    run_state_dir = state_dir / "runs" / resolved_run_date
    run_logs_dir = logs_dir / "runs" / resolved_run_date
    signals_dir = run_state_dir / "signals"
    planner_dir = run_state_dir / "planner"
    archive_dir = run_state_dir / "archive"
    market_feed_dir = _resolve_env_path(agent_root, "MARKET_FEED_DIR", run_state_dir / "market_feed")
    return RuntimePaths(
        agent_root=agent_root,
        config_dir=agent_root / "config",
        scripts_dir=agent_root / "scripts",
        state_dir=state_dir,
        logs_dir=logs_dir,
        reports_dir=agent_root / "reports",
        run_date=resolved_run_date,
        run_state_dir=run_state_dir,
        run_logs_dir=run_logs_dir,
        signals_dir=signals_dir,
        planner_dir=planner_dir,
        archive_dir=archive_dir,
        market_feed_dir=market_feed_dir,
        dsa_signals_path=_resolve_env_path(agent_root, "DSA_SIGNALS_PATH", signals_dir / "dsa_signals.json"),
        kronos_signals_path=_resolve_env_path(agent_root, "KRONOS_SIGNALS_PATH", signals_dir / "kronos_signals.json"),
        technical_signals_path=_resolve_env_path(agent_root, "TECHNICAL_SIGNALS_PATH", signals_dir / "technical_signals.json"),
        daily_plan_path=_resolve_env_path(agent_root, "DAILY_PLAN_PATH", planner_dir / "daily_plan.json"),
        daily_plan_markdown_path=_resolve_env_path(agent_root, "DAILY_PLAN_MARKDOWN_PATH", planner_dir / "daily_plan.md"),
        dynamic_allowlist_path=_resolve_env_path(agent_root, "DYNAMIC_ALLOWLIST_PATH", planner_dir / "dynamic_allowlist.json"),
        today_allowlist_path=_resolve_env_path(agent_root, "TODAY_ALLOWLIST_PATH", planner_dir / "today_allowlist.txt"),
        daily_usage_path=_resolve_env_path(agent_root, "DAILY_USAGE_PATH", planner_dir / "daily_usage.json"),
        decisions_log_path=_resolve_env_path(agent_root, "DECISIONS_LOG_PATH", run_logs_dir / "decisions.jsonl"),
        orders_log_path=_resolve_env_path(agent_root, "ORDERS_LOG_PATH", run_logs_dir / "orders.jsonl"),
        codex_run_log_path=_resolve_env_path(agent_root, "CODEX_RUN_LOG_PATH", run_logs_dir / "codex_runs.log"),
        error_log_path=_resolve_env_path(agent_root, "ERROR_LOG_PATH", run_logs_dir / "errors.log"),
        postmarket_summary_path=_resolve_env_path(agent_root, "POSTMARKET_SUMMARY_PATH", run_logs_dir / "postmarket_summary.md"),
    )
