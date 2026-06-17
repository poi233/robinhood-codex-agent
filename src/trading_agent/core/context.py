from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

from trading_agent.core.time import pt_date_string


def resolve_agent_root() -> Path:
    """Resolve the repository root from the installed package location.

    LaunchAgents and cron jobs can run with an arbitrary current working directory.
    The trading agent should therefore derive its repo root from the code location,
    not from ``cwd``.
    """

    env_root = os.environ.get("AGENT_ROOT")
    if env_root:
        candidate = Path(env_root).expanduser().resolve()
        if (candidate / "src" / "trading_agent").exists() and (candidate / "src" / "config").exists():
            return candidate

    cwd = Path.cwd()
    if (cwd / "KILL_SWITCH").exists() or ((cwd / "src" / "config").exists() and (cwd / "src" / "trading_agent").exists()):
        return cwd

    for candidate in Path(__file__).resolve().parents:
        if (candidate / "KILL_SWITCH").exists() or ((candidate / "src" / "config").exists() and (candidate / "src" / "trading_agent").exists()):
            return candidate

    return Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class RuntimePaths:
    agent_root: Path
    src_dir: Path
    package_dir: Path
    config_dir: Path
    prompts_dir: Path
    scripts_dir: Path
    runtime_dir: Path
    state_dir: Path
    logs_dir: Path
    reports_dir: Path
    run_date: str
    run_state_dir: Path
    run_logs_dir: Path
    signals_dir: Path
    planner_dir: Path
    paper_dir: Path
    archive_dir: Path
    market_feed_dir: Path
    ohlcv_cache_dir: Path
    dsa_signals_path: Path
    kronos_signals_path: Path
    technical_signals_path: Path
    technical_signals_full_path: Path
    technical_features_path: Path
    dsa_metrics_path: Path
    factor_panel_path: Path
    factor_alpha_path: Path
    ai_signals_path: Path
    trader_watch_levels_path: Path
    daily_plan_path: Path
    daily_plan_markdown_path: Path
    daily_plan_zh_markdown_path: Path
    dynamic_allowlist_path: Path
    today_allowlist_path: Path
    daily_usage_path: Path
    account_snapshot_path: Path
    capital_snapshot_path: Path
    market_calendar_path: Path
    quote_snapshot_core_path: Path
    candidate_snapshot_path: Path
    candidate_scores_path: Path
    quote_snapshot_candidates_path: Path
    tradability_snapshot_path: Path
    catalyst_snapshot_path: Path
    data_status_summary_path: Path
    risk_overlay_path: Path
    premarket_diagnostics_path: Path
    paper_account_path: Path
    paper_positions_path: Path
    paper_orders_log_path: Path
    paper_day_start_path: Path
    paper_day_end_path: Path
    paper_equity_curve_path: Path
    paper_postmarket_summary_path: Path
    decisions_log_path: Path
    intraday_rankings_log_path: Path
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
    src_dir = agent_root / "src"
    package_dir = src_dir / "trading_agent"
    runtime_dir = agent_root / "runtime"
    state_dir = runtime_dir / "state"
    logs_dir = runtime_dir / "logs"
    reports_dir = runtime_dir / "reports"
    run_state_dir = state_dir / "runs" / resolved_run_date
    run_logs_dir = logs_dir / "runs" / resolved_run_date
    signals_dir = run_state_dir / "signals"
    planner_dir = run_state_dir / "planner"
    paper_dir = run_state_dir / "paper"
    archive_dir = run_state_dir / "archive"
    market_feed_dir = _resolve_env_path(agent_root, "MARKET_FEED_DIR", run_state_dir / "market_feed")
    ohlcv_cache_dir = _resolve_env_path(agent_root, "OHLCV_CACHE_DIR", runtime_dir / "cache" / "ohlcv")
    return RuntimePaths(
        agent_root=agent_root,
        src_dir=src_dir,
        package_dir=package_dir,
        config_dir=src_dir / "config",
        prompts_dir=src_dir / "prompts",
        scripts_dir=src_dir / "scripts",
        runtime_dir=runtime_dir,
        state_dir=state_dir,
        logs_dir=logs_dir,
        reports_dir=reports_dir,
        run_date=resolved_run_date,
        run_state_dir=run_state_dir,
        run_logs_dir=run_logs_dir,
        signals_dir=signals_dir,
        planner_dir=planner_dir,
        paper_dir=paper_dir,
        archive_dir=archive_dir,
        market_feed_dir=market_feed_dir,
        ohlcv_cache_dir=ohlcv_cache_dir,
        dsa_signals_path=_resolve_env_path(agent_root, "DSA_SIGNALS_PATH", signals_dir / "dsa_signals.json"),
        kronos_signals_path=_resolve_env_path(agent_root, "KRONOS_SIGNALS_PATH", signals_dir / "kronos_signals.json"),
        technical_signals_path=_resolve_env_path(agent_root, "TECHNICAL_SIGNALS_PATH", signals_dir / "technical_signals.json"),
        technical_signals_full_path=_resolve_env_path(agent_root, "TECHNICAL_SIGNALS_FULL_PATH", signals_dir / "technical_signals.full.json"),
        technical_features_path=_resolve_env_path(agent_root, "TECHNICAL_FEATURES_PATH", signals_dir / "technical_features.json"),
        dsa_metrics_path=_resolve_env_path(agent_root, "DSA_METRICS_PATH", signals_dir / "dsa_metrics.json"),
        factor_panel_path=_resolve_env_path(agent_root, "FACTOR_PANEL_PATH", signals_dir / "factor_panel.json"),
        factor_alpha_path=_resolve_env_path(agent_root, "FACTOR_ALPHA_PATH", planner_dir / "factor_alpha.json"),
        ai_signals_path=_resolve_env_path(agent_root, "AI_SIGNALS_PATH", signals_dir / "ai_signals.json"),
        trader_watch_levels_path=_resolve_env_path(agent_root, "TRADER_WATCH_LEVELS_PATH", planner_dir / "trader_watch_levels.json"),
        daily_plan_path=_resolve_env_path(agent_root, "DAILY_PLAN_PATH", planner_dir / "daily_plan.json"),
        daily_plan_markdown_path=_resolve_env_path(agent_root, "DAILY_PLAN_MARKDOWN_PATH", planner_dir / "daily_plan.md"),
        daily_plan_zh_markdown_path=_resolve_env_path(agent_root, "DAILY_PLAN_ZH_MARKDOWN_PATH", planner_dir / "daily_plan.zh.md"),
        dynamic_allowlist_path=_resolve_env_path(agent_root, "DYNAMIC_ALLOWLIST_PATH", planner_dir / "dynamic_allowlist.json"),
        today_allowlist_path=_resolve_env_path(agent_root, "TODAY_ALLOWLIST_PATH", planner_dir / "today_allowlist.txt"),
        daily_usage_path=_resolve_env_path(agent_root, "DAILY_USAGE_PATH", planner_dir / "daily_usage.json"),
        account_snapshot_path=_resolve_env_path(agent_root, "ACCOUNT_SNAPSHOT_PATH", planner_dir / "account_snapshot.json"),
        capital_snapshot_path=_resolve_env_path(agent_root, "CAPITAL_SNAPSHOT_PATH", planner_dir / "capital_snapshot.json"),
        market_calendar_path=_resolve_env_path(agent_root, "MARKET_CALENDAR_PATH", planner_dir / "market_calendar.json"),
        quote_snapshot_core_path=_resolve_env_path(agent_root, "QUOTE_SNAPSHOT_CORE_PATH", planner_dir / "quote_snapshot_core.json"),
        candidate_snapshot_path=_resolve_env_path(agent_root, "CANDIDATE_SNAPSHOT_PATH", planner_dir / "candidate_snapshot.json"),
        candidate_scores_path=_resolve_env_path(agent_root, "CANDIDATE_SCORES_PATH", planner_dir / "candidate_scores.json"),
        quote_snapshot_candidates_path=_resolve_env_path(agent_root, "QUOTE_SNAPSHOT_CANDIDATES_PATH", planner_dir / "quote_snapshot_candidates.json"),
        tradability_snapshot_path=_resolve_env_path(agent_root, "TRADABILITY_SNAPSHOT_PATH", planner_dir / "tradability_snapshot.json"),
        catalyst_snapshot_path=_resolve_env_path(agent_root, "CATALYST_SNAPSHOT_PATH", planner_dir / "catalyst_snapshot.json"),
        data_status_summary_path=_resolve_env_path(agent_root, "DATA_STATUS_SUMMARY_PATH", planner_dir / "data_status_summary.json"),
        risk_overlay_path=_resolve_env_path(agent_root, "RISK_OVERLAY_PATH", planner_dir / "risk_overlay.json"),
        premarket_diagnostics_path=_resolve_env_path(agent_root, "PREMARKET_DIAGNOSTICS_PATH", planner_dir / "premarket_diagnostics.json"),
        paper_account_path=_resolve_env_path(agent_root, "PAPER_ACCOUNT_PATH", paper_dir / "account.json"),
        paper_positions_path=_resolve_env_path(agent_root, "PAPER_POSITIONS_PATH", paper_dir / "positions.json"),
        paper_orders_log_path=_resolve_env_path(agent_root, "PAPER_ORDERS_LOG_PATH", paper_dir / "orders.jsonl"),
        paper_day_start_path=_resolve_env_path(agent_root, "PAPER_DAY_START_PATH", paper_dir / "day_start.json"),
        paper_day_end_path=_resolve_env_path(agent_root, "PAPER_DAY_END_PATH", paper_dir / "day_end.json"),
        paper_equity_curve_path=_resolve_env_path(agent_root, "PAPER_EQUITY_CURVE_PATH", paper_dir / "equity_curve.jsonl"),
        paper_postmarket_summary_path=_resolve_env_path(agent_root, "PAPER_POSTMARKET_SUMMARY_PATH", paper_dir / "postmarket_summary.json"),
        decisions_log_path=_resolve_env_path(agent_root, "DECISIONS_LOG_PATH", run_logs_dir / "audit" / "decisions.jsonl"),
        intraday_rankings_log_path=_resolve_env_path(agent_root, "INTRADAY_RANKINGS_LOG_PATH", run_logs_dir / "audit" / "intraday_rankings.jsonl"),
        orders_log_path=_resolve_env_path(agent_root, "ORDERS_LOG_PATH", run_logs_dir / "audit" / "orders.jsonl"),
        codex_run_log_path=_resolve_env_path(agent_root, "CODEX_RUN_LOG_PATH", run_logs_dir / "outputs" / "codex_runs.log"),
        error_log_path=_resolve_env_path(agent_root, "ERROR_LOG_PATH", run_logs_dir / "system" / "errors.log"),
        postmarket_summary_path=_resolve_env_path(agent_root, "POSTMARKET_SUMMARY_PATH", run_logs_dir / "reports" / "postmarket_summary.md"),
    )


@dataclass(frozen=True)
class ExperimentPaths:
    """Isolated ledger paths for one shadow challenger (G-pre remainder for G6).

    Everything roots under runtime/state/runs/<date>/experiments/<strategy_id>/ so a
    challenger's shadow decisions/orders/equity can never overlap the champion's paper ledger.
    """

    experiment_dir: Path
    shadow_decisions_log_path: Path
    shadow_orders_log_path: Path
    shadow_equity_curve_path: Path


def build_experiment_paths(agent_root: Path, *, run_date: str | None = None, strategy_id: str) -> ExperimentPaths:
    base = build_runtime_paths(agent_root, run_date=run_date).run_state_dir / "experiments" / strategy_id
    return ExperimentPaths(
        experiment_dir=base,
        shadow_decisions_log_path=base / "shadow_decisions.jsonl",
        shadow_orders_log_path=base / "shadow_orders.jsonl",
        shadow_equity_curve_path=base / "shadow_equity_curve.jsonl",
    )


def build_experiment_runtime_paths(agent_root: Path, *, run_date: str | None = None, strategy_id: str) -> RuntimePaths:
    """A RuntimePaths identical to the champion's except the paper ledger + daily_usage are rooted
    under runtime/state/runs/<date>/experiments/<strategy_id>/paper/. This lets the paper broker
    simulate a challenger's fills in a fully isolated ledger (G9) — the champion paper/* is never
    touched. All non-paper paths (configs, signals, planner artifacts) stay shared with the champion."""
    base = build_runtime_paths(agent_root, run_date=run_date)
    paper = base.run_state_dir / "experiments" / strategy_id / "paper"
    return replace(
        base,
        paper_account_path=paper / "account.json",
        paper_positions_path=paper / "positions.json",
        paper_orders_log_path=paper / "orders.jsonl",
        paper_equity_curve_path=paper / "equity_curve.jsonl",
        paper_day_start_path=paper / "day_start.json",
        paper_day_end_path=paper / "day_end.json",
        paper_postmarket_summary_path=paper / "postmarket_summary.json",
        daily_usage_path=paper / "daily_usage.json",
    )
