from __future__ import annotations

import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from trading_agent.core.io import write_json
from trading_agent.replay.analysis import discover_run_dates

# N4 — data retention / archival. runtime/state/runs/<date>/ grows every trading day. The dominant
# disk hog is market_feed/ (OHLCV JSON + chart PNGs + news for the whole universe) — a premarket
# INPUT snapshot that no post-hoc analysis reads (calibration pulls forward returns from yfinance;
# replay/build read the small decision/order/score JSON). So for runs older than a retention window,
# we PRUNE those big artifacts while keeping every analysis input intact.
#
# HARD RED LINES:
#   - Default DRY-RUN: nothing is deleted unless apply=True is passed explicitly.
#   - Never touches runs inside the retention window (most-recent keep_days).
#   - Only removes the configured prune dirs (default: market_feed); never the analysis JSON/JSONL,
#     never src/config, never KILL_SWITCH, never anything outside runtime/state|logs/runs/<date>/.
#   - Calibration/replay/analytics build must still run on a pruned run (they don't read market_feed).

DEFAULT_KEEP_DAYS = 60
# Per-run subdirectories safe to prune (relative to the run's state dir). market_feed is the big one;
# the list is extensible but every entry must be a regenerable INPUT snapshot, not an analysis input.
DEFAULT_PRUNE_DIRS = ("market_feed",)


def _dir_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _run_state_dir(agent_root: Path, run_date: str) -> Path:
    return agent_root / "runtime" / "state" / "runs" / run_date


def plan_retention(
    agent_root: Path,
    *,
    keep_days: int = DEFAULT_KEEP_DAYS,
    today: str | None = None,
    prune_dirs: tuple[str, ...] = DEFAULT_PRUNE_DIRS,
) -> dict[str, Any]:
    """Pure-ish (reads filesystem sizes, deletes nothing): list which old runs' big artifacts would
    be pruned and how much disk that reclaims. A run is eligible when its date is strictly older than
    today - keep_days. Runs inside the window are kept fully intact."""
    today_date = date.fromisoformat(today) if today else datetime.now(timezone.utc).date()
    run_dates = discover_run_dates(agent_root)

    kept: list[str] = []
    prune_runs: list[dict[str, Any]] = []
    total_reclaim = 0
    for run_date in run_dates:
        try:
            age_days = (today_date - date.fromisoformat(run_date)).days
        except ValueError:
            kept.append(run_date)  # unparseable date: be safe, keep it
            continue
        if age_days <= keep_days:
            kept.append(run_date)
            continue
        state_dir = _run_state_dir(agent_root, run_date)
        targets = []
        run_bytes = 0
        for sub in prune_dirs:
            target = state_dir / sub
            if target.exists():
                size = _dir_size_bytes(target)
                targets.append({"path": str(target), "bytes": size})
                run_bytes += size
        if targets:
            prune_runs.append({"run_date": run_date, "age_days": age_days,
                               "targets": targets, "bytes": run_bytes})
            total_reclaim += run_bytes
        else:
            kept.append(run_date)  # nothing prunable left (already pruned) -> effectively kept

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": 1,
        "keep_days": keep_days,
        "today": today_date.isoformat(),
        "prune_dirs": list(prune_dirs),
        "run_date_count": len(run_dates),
        "kept_run_count": len(kept),
        "prune_run_count": len(prune_runs),
        "total_reclaim_bytes": total_reclaim,
        "prune_runs": prune_runs,
        "note": "Retention plan (N4). Prunes only regenerable premarket input snapshots "
                "(market_feed) from runs older than keep_days; keeps all analysis inputs. "
                "Dry-run unless applied. Calibration/replay/build still run on pruned runs.",
    }


def apply_retention(plan: dict[str, Any]) -> dict[str, Any]:
    """Delete the directories listed in a retention plan. Returns reclaimed bytes + removed count.
    Only ever removes paths the plan computed (which are under runtime/state/runs/<date>/<prune_dir>)."""
    removed = 0
    reclaimed = 0
    errors: list[str] = []
    for run in plan.get("prune_runs") or []:
        for target in run.get("targets") or []:
            path = Path(target["path"])
            if not path.exists():
                continue
            try:
                shutil.rmtree(path)
                removed += 1
                reclaimed += int(target.get("bytes") or 0)
            except OSError as exc:
                errors.append(f"{path}: {exc}")
    return {"removed_dirs": removed, "reclaimed_bytes": reclaimed, "errors": errors}


def default_retention_report_path(agent_root: Path) -> Path:
    return agent_root / "runtime" / "analytics" / "retention_report.json"


def default_retention_md_path(agent_root: Path) -> Path:
    return agent_root / "runtime" / "analytics" / "retention_report.md"


def _human_mb(num_bytes: int) -> str:
    return f"{num_bytes / (1024 * 1024):.1f} MB"


def format_retention_markdown(plan: dict[str, Any], applied: dict[str, Any] | None) -> str:
    mode = "APPLIED" if applied else "DRY-RUN (nothing deleted)"
    lines = [
        "# Data Retention (N4)",
        "",
        f"_Generated {plan['generated_at']}._  ·  keep_days: {plan['keep_days']}  ·  today: {plan['today']}",
        "",
        f"**Mode: {mode}**  ·  prune dirs: `{', '.join(plan['prune_dirs'])}`",
        "",
        f"- run dates total: {plan['run_date_count']}",
        f"- kept (within window / nothing to prune): {plan['kept_run_count']}",
        f"- prunable runs: {plan['prune_run_count']}",
        f"- reclaimable: {_human_mb(plan['total_reclaim_bytes'])}",
    ]
    if applied:
        lines.append(f"- **removed dirs: {applied['removed_dirs']}  ·  reclaimed: {_human_mb(applied['reclaimed_bytes'])}**")
        if applied.get("errors"):
            lines.append(f"- errors: {applied['errors']}")
    if plan["prune_runs"]:
        lines += ["", "## Prunable runs", ""]
        for run in plan["prune_runs"]:
            lines.append(f"- **{run['run_date']}** (age {run['age_days']}d): {_human_mb(run['bytes'])}")
    else:
        lines += ["", "_No runs old enough to prune._"]
    return "\n".join(lines) + "\n"


def write_retention_report(
    agent_root: Path,
    *,
    keep_days: int = DEFAULT_KEEP_DAYS,
    apply: bool = False,
    today: str | None = None,
    prune_dirs: tuple[str, ...] = DEFAULT_PRUNE_DIRS,
) -> tuple[Path, dict[str, Any]]:
    """Plan retention, optionally apply (delete), and write retention_report.{json,md}.
    Returns (json_path, result) where result carries the plan and, if applied, the deletion summary."""
    plan = plan_retention(agent_root, keep_days=keep_days, today=today, prune_dirs=prune_dirs)
    applied = apply_retention(plan) if apply else None

    report = dict(plan)
    report["mode"] = "applied" if apply else "dry_run"
    if applied is not None:
        report["applied"] = applied

    json_path = default_retention_report_path(agent_root)
    md_path = default_retention_md_path(agent_root)
    write_json(json_path, report)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(format_retention_markdown(plan, applied), encoding="utf-8")
    return json_path, report
