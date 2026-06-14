from __future__ import annotations

import os
from pathlib import Path

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.time import pt_now


def build_runtime_block(run_kind: str, agent_root: Path) -> str:
    env = os.environ
    paths = build_runtime_paths(agent_root)
    values = {
        "RUN_KIND": run_kind,
        "RUN_STARTED_AT": pt_now().strftime("%Y-%m-%dT%H:%M:%S%z"),
        "RUN_DATE_PT": paths.run_date,
        "TIMEZONE": "America/Los_Angeles",
        "AGENT_ROOT": str(agent_root),
        "SRC_DIR": str(paths.src_dir),
        "PACKAGE_DIR": str(paths.package_dir),
        "CONFIG_DIR": str(paths.config_dir),
        "PROMPTS_DIR": str(paths.prompts_dir),
        "SCRIPTS_DIR": str(paths.scripts_dir),
        "RUNTIME_DIR": str(paths.runtime_dir),
        "RUN_STATE_DIR": str(paths.run_state_dir),
        "RUN_LOGS_DIR": str(paths.run_logs_dir),
        "SIGNALS_DIR": str(paths.signals_dir),
        "PLANNER_DIR": str(paths.planner_dir),
        "PAPER_DIR": str(paths.paper_dir),
        "ARCHIVE_DIR": str(paths.archive_dir),
        "TRADING_MODE": env.get("TRADING_MODE", "paper"),
        "RISK_TIER": env.get("RISK_TIER", "0"),
        "KILL_SWITCH_STATUS": "present" if (agent_root / "KILL_SWITCH").exists() else "absent",
        "ALLOW_OUTSIDE_MARKET_TEST": env.get("ALLOW_OUTSIDE_MARKET_TEST", "0"),
        "MAX_SINGLE_ORDER_NOTIONAL": env.get("MAX_SINGLE_ORDER_NOTIONAL", "10"),
        "MAX_DAILY_NOTIONAL": env.get("MAX_DAILY_NOTIONAL", "25"),
        "PAPER_STARTING_CASH": env.get("PAPER_STARTING_CASH", "400000"),
        "CODEX_EXEC_DRY_RUN": env.get("CODEX_EXEC_DRY_RUN", "0"),
        "ENABLE_DSA_SIGNAL_LAYER": env.get("ENABLE_DSA_SIGNAL_LAYER", "1"),
        "ENABLE_MARKET_FEED_LAYER": env.get("ENABLE_MARKET_FEED_LAYER", "1"),
        "ENABLE_TECHNICAL_SIGNAL_LAYER": env.get("ENABLE_TECHNICAL_SIGNAL_LAYER", "1"),
        "MARKET_FEED_DIR": str(paths.market_feed_dir),
        "DSA_SIGNALS_PATH": str(paths.dsa_signals_path),
        "KRONOS_SIGNALS_PATH": str(paths.kronos_signals_path),
        "TECHNICAL_SIGNALS_PATH": str(paths.technical_signals_path),
        "TRADER_WATCH_LEVELS_PATH": str(paths.trader_watch_levels_path),
        "DAILY_PLAN_PATH": str(paths.daily_plan_path),
        "DAILY_PLAN_MARKDOWN_PATH": str(paths.daily_plan_markdown_path),
        "DYNAMIC_ALLOWLIST_PATH": str(paths.dynamic_allowlist_path),
        "TODAY_ALLOWLIST_PATH": str(paths.today_allowlist_path),
        "DAILY_USAGE_PATH": str(paths.daily_usage_path),
        "ACCOUNT_SNAPSHOT_PATH": str(paths.account_snapshot_path),
        "CAPITAL_SNAPSHOT_PATH": str(paths.capital_snapshot_path),
        "MARKET_CALENDAR_PATH": str(paths.market_calendar_path),
        "QUOTE_SNAPSHOT_CORE_PATH": str(paths.quote_snapshot_core_path),
        "CANDIDATE_SNAPSHOT_PATH": str(paths.candidate_snapshot_path),
        "CANDIDATE_SCORES_PATH": str(paths.candidate_scores_path),
        "QUOTE_SNAPSHOT_CANDIDATES_PATH": str(paths.quote_snapshot_candidates_path),
        "TRADABILITY_SNAPSHOT_PATH": str(paths.tradability_snapshot_path),
        "CATALYST_SNAPSHOT_PATH": str(paths.catalyst_snapshot_path),
        "DATA_STATUS_SUMMARY_PATH": str(paths.data_status_summary_path),
        "RISK_OVERLAY_PATH": str(paths.risk_overlay_path),
        "PAPER_ACCOUNT_PATH": str(paths.paper_account_path),
        "PAPER_POSITIONS_PATH": str(paths.paper_positions_path),
        "PAPER_ORDERS_LOG_PATH": str(paths.paper_orders_log_path),
        "PAPER_DAY_START_PATH": str(paths.paper_day_start_path),
        "PAPER_DAY_END_PATH": str(paths.paper_day_end_path),
        "PAPER_EQUITY_CURVE_PATH": str(paths.paper_equity_curve_path),
        "DECISIONS_LOG_PATH": str(paths.decisions_log_path),
        "ORDERS_LOG_PATH": str(paths.orders_log_path),
        "POSTMARKET_SUMMARY_PATH": str(paths.postmarket_summary_path),
    }
    lines = ["<runtime>"]
    lines.extend(f"{key}={value}" for key, value in values.items())
    lines.append("</runtime>")
    lines.append("")
    return "\n".join(lines)
