from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import ensure_dir


def daily_state_run_dir(agent_root: Path, run_date: str) -> Path:
    return build_runtime_paths(agent_root, run_date=run_date).run_state_dir


def daily_logs_run_dir(agent_root: Path, run_date: str) -> Path:
    return build_runtime_paths(agent_root, run_date=run_date).run_logs_dir


def _pipeline_log_path(agent_root: Path, run_date: str) -> Path:
    return daily_logs_run_dir(agent_root, run_date) / "pipeline" / "pipeline.jsonl"


def _progress_log_path(agent_root: Path, run_date: str, run_kind: str) -> Path:
    return daily_logs_run_dir(agent_root, run_date) / "progress" / f"{run_kind}.jsonl"


def _output_log_path(agent_root: Path, run_date: str, run_kind: str, stream: str) -> Path:
    return daily_logs_run_dir(agent_root, run_date) / "outputs" / stream / f"{run_kind}.log"


def append_stage_log(
    agent_root: Path,
    run_date: str,
    stage: str,
    status: str,
    message: str,
    *,
    elapsed_seconds: float | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "timestamp": datetime.now().astimezone().isoformat(),
        "date": run_date,
        "stage": stage,
        "status": status,
        "message": message,
    }
    if elapsed_seconds is not None:
        payload["elapsed_seconds"] = round(elapsed_seconds, 3)
    if details:
        payload["details"] = details

    output = _pipeline_log_path(agent_root, run_date)
    ensure_dir(output.parent)
    with output.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def append_run_output_log(
    agent_root: Path,
    run_date: str,
    run_kind: str,
    stream: str,
    content: str,
) -> None:
    if not content:
        return
    output = _output_log_path(agent_root, run_date, run_kind, stream)
    ensure_dir(output.parent)
    with output.open("a", encoding="utf-8") as handle:
        handle.write(content)
        if not content.endswith("\n"):
            handle.write("\n")


def append_prompt_progress_log(
    agent_root: Path,
    run_date: str,
    run_kind: str,
    status: str,
    message: str,
    *,
    details: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "timestamp": datetime.now().astimezone().isoformat(),
        "date": run_date,
        "run_kind": run_kind,
        "status": status,
        "message": message,
    }
    if details:
        payload["details"] = details
    output = _progress_log_path(agent_root, run_date, run_kind)
    ensure_dir(output.parent)
    with output.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def snapshot_stage_artifacts(agent_root: Path, run_date: str, stage: str) -> list[str]:
    paths = build_runtime_paths(agent_root, run_date=run_date)
    run_dir = paths.run_state_dir

    mappings: dict[str, list[tuple[Path, Path]]] = {
        "dsa": [
            (paths.dsa_signals_path, run_dir / "signals" / "dsa_signals.json"),
        ],
        "kronos": [
            (paths.kronos_signals_path, run_dir / "signals" / "kronos_signals.json"),
        ],
        "technical": [
            (paths.technical_signals_path, run_dir / "signals" / "technical_signals.json"),
        ],
        "trader_watch_levels": [
            (paths.trader_watch_levels_path, run_dir / "planner" / "trader_watch_levels.json"),
        ],
        "account_snapshot": [
            (paths.account_snapshot_path, run_dir / "planner" / "account_snapshot.json"),
        ],
        "capital_snapshot": [
            (paths.capital_snapshot_path, run_dir / "planner" / "capital_snapshot.json"),
        ],
        "market_calendar": [
            (paths.market_calendar_path, run_dir / "planner" / "market_calendar.json"),
        ],
        "quote_snapshot_core": [
            (paths.quote_snapshot_core_path, run_dir / "planner" / "quote_snapshot_core.json"),
        ],
        "candidate_merge": [
            (paths.candidate_snapshot_path, run_dir / "planner" / "candidate_snapshot.json"),
        ],
        "candidate_scoring": [
            (paths.candidate_scores_path, run_dir / "planner" / "candidate_scores.json"),
        ],
        "quote_snapshot_candidates": [
            (paths.quote_snapshot_candidates_path, run_dir / "planner" / "quote_snapshot_candidates.json"),
        ],
        "tradability_candidates": [
            (paths.tradability_snapshot_path, run_dir / "planner" / "tradability_snapshot.json"),
        ],
        "catalyst_enrichment": [
            (paths.catalyst_snapshot_path, run_dir / "planner" / "catalyst_snapshot.json"),
        ],
        "data_status_summary": [
            (paths.data_status_summary_path, run_dir / "planner" / "data_status_summary.json"),
        ],
        "risk_overlay": [
            (paths.risk_overlay_path, run_dir / "planner" / "risk_overlay.json"),
        ],
        "premarket_diagnostics": [
            (paths.premarket_diagnostics_path, run_dir / "planner" / "premarket_diagnostics.json"),
        ],
        "planner": [
            (paths.account_snapshot_path, run_dir / "planner" / "account_snapshot.json"),
            (paths.capital_snapshot_path, run_dir / "planner" / "capital_snapshot.json"),
            (paths.market_calendar_path, run_dir / "planner" / "market_calendar.json"),
            (paths.quote_snapshot_core_path, run_dir / "planner" / "quote_snapshot_core.json"),
            (paths.candidate_snapshot_path, run_dir / "planner" / "candidate_snapshot.json"),
            (paths.candidate_scores_path, run_dir / "planner" / "candidate_scores.json"),
            (paths.quote_snapshot_candidates_path, run_dir / "planner" / "quote_snapshot_candidates.json"),
            (paths.tradability_snapshot_path, run_dir / "planner" / "tradability_snapshot.json"),
            (paths.catalyst_snapshot_path, run_dir / "planner" / "catalyst_snapshot.json"),
            (paths.trader_watch_levels_path, run_dir / "planner" / "trader_watch_levels.json"),
            (paths.data_status_summary_path, run_dir / "planner" / "data_status_summary.json"),
            (paths.risk_overlay_path, run_dir / "planner" / "risk_overlay.json"),
            (paths.premarket_diagnostics_path, run_dir / "planner" / "premarket_diagnostics.json"),
            (paths.daily_plan_path, run_dir / "planner" / "daily_plan.json"),
            (paths.daily_plan_markdown_path, run_dir / "planner" / "daily_plan.md"),
            (paths.daily_plan_zh_markdown_path, run_dir / "planner" / "daily_plan.zh.md"),
            (paths.dynamic_allowlist_path, run_dir / "planner" / "dynamic_allowlist.json"),
            (paths.today_allowlist_path, run_dir / "planner" / "today_allowlist.txt"),
            (paths.daily_usage_path, run_dir / "planner" / "daily_usage.json"),
        ],
        "final_planner": [
            (paths.data_status_summary_path, run_dir / "planner" / "data_status_summary.json"),
            (paths.candidate_scores_path, run_dir / "planner" / "candidate_scores.json"),
            (paths.risk_overlay_path, run_dir / "planner" / "risk_overlay.json"),
            (paths.premarket_diagnostics_path, run_dir / "planner" / "premarket_diagnostics.json"),
            (paths.daily_plan_path, run_dir / "planner" / "daily_plan.json"),
            (paths.daily_plan_markdown_path, run_dir / "planner" / "daily_plan.md"),
            (paths.daily_plan_zh_markdown_path, run_dir / "planner" / "daily_plan.zh.md"),
            (paths.dynamic_allowlist_path, run_dir / "planner" / "dynamic_allowlist.json"),
            (paths.today_allowlist_path, run_dir / "planner" / "today_allowlist.txt"),
            (paths.daily_usage_path, run_dir / "planner" / "daily_usage.json"),
        ],
        "market_context": [
            (paths.market_feed_dir / "manifest.json", run_dir / "market_feed" / "manifest.json"),
        ],
        "archive": [
            (paths.archive_dir / "premarket_report.json", run_dir / "archive" / "premarket_report.json"),
        ],
    }

    copied: list[str] = []
    for source, target in mappings.get(stage, []):
        if not source.exists():
            continue
        if source.resolve() == target.resolve():
            copied.append(str(target.relative_to(agent_root)))
            continue
        ensure_dir(target.parent)
        shutil.copy2(source, target)
        copied.append(str(target.relative_to(agent_root)))
    return copied
