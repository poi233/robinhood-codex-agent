from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_agent.core.io import read_json, write_json

# L4 — nightly health / freshness. The nightly batch is best-effort (a failing step is logged and the
# batch continues), which risks "looks healthy, but some step has been failing for days". This module
# surfaces that: it flags reports that have gone stale (their generating step has effectively stopped
# producing) and reads the per-step pass/fail the nightly script records. Pure read; never trades.

STALE_HOURS = 30  # nightly runs daily; a report older than this means last night's step didn't refresh it

# The reports the nightly batch is expected to refresh; a stale/absent one points at a failing step.
_REPORTS = (
    "calibration_report.json",
    "fill_quality_report.json",
    "ai_signal_study.json",
    "ai_ablation.json",
    "weight_suggestion.json",
    "growth_observations.json",
    "experiment_report.json",
)


def _age_hours(generated_at: Any, now: datetime) -> float | None:
    if not isinstance(generated_at, str) or not generated_at:
        return None
    try:
        ts = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return round((now - ts).total_seconds() / 3600.0, 1)


def _read_step_results(agent_root: Path) -> tuple[str | None, list[str], str | None]:
    """Most recent nightly run's per-step results, if the batch wrote them. Returns
    (run_date, failed_step_labels, finished_at)."""
    from trading_agent.replay.analysis import discover_run_dates

    for run_date in reversed(discover_run_dates(agent_root)):
        path = agent_root / "runtime" / "logs" / "runs" / run_date / "nightly" / "step_results.jsonl"
        if not path.exists():
            continue
        failed: list[str] = []
        finished_at: str | None = None
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            finished_at = row.get("timestamp") or finished_at
            if str(row.get("status") or "").lower() not in {"ok", "completed", "success"}:
                failed.append(str(row.get("step") or "?"))
        return run_date, failed, finished_at
    return None, [], None


def build_nightly_health(agent_root: Path, *, now: datetime | None = None, stale_hours: int = STALE_HOURS) -> dict[str, Any]:
    """Assemble the nightly health snapshot: per-report freshness + the last run's failed steps.
    `status` is `ok` only when nothing is stale and no step failed."""
    now = now or datetime.now(timezone.utc)
    analytics = agent_root / "runtime" / "analytics"
    reports: list[dict[str, Any]] = []
    for name in _REPORTS:
        path = analytics / name
        if not path.exists():
            reports.append({"report": name, "present": False, "age_hours": None, "stale": True})
            continue
        payload = read_json(path)
        gen = payload.get("generated_at") if isinstance(payload, dict) else None
        age = _age_hours(gen, now)
        reports.append({"report": name, "present": True, "generated_at": gen, "age_hours": age,
                        "stale": age is None or age > stale_hours})
    stale_reports = [r["report"] for r in reports if r["stale"]]
    last_run_date, failed_steps, finished_at = _read_step_results(agent_root)
    return {
        "generated_at": now.isoformat(),
        "status": "ok" if not stale_reports and not failed_steps else "attention",
        "stale_hours_threshold": stale_hours,
        "last_nightly_run_date": last_run_date,
        "last_nightly_finished_at": finished_at,
        "failed_steps": failed_steps,
        "stale_reports": stale_reports,
        "reports": reports,
    }


def default_nightly_health_path(agent_root: Path) -> Path:
    return agent_root / "runtime" / "analytics" / "nightly_health.json"


def write_nightly_health(agent_root: Path) -> Path:
    out = default_nightly_health_path(agent_root)
    write_json(out, build_nightly_health(agent_root))
    return out
