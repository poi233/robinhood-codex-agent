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

    output = daily_logs_run_dir(agent_root, run_date) / "pipeline.jsonl"
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
    output = daily_logs_run_dir(agent_root, run_date) / f"{run_kind}.{stream}.log"
    ensure_dir(output.parent)
    with output.open("a", encoding="utf-8") as handle:
        handle.write(content)
        if not content.endswith("\n"):
            handle.write("\n")


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
        "planner": [
            (paths.daily_plan_path, run_dir / "planner" / "daily_plan.json"),
            (paths.daily_plan_markdown_path, run_dir / "planner" / "daily_plan.md"),
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
