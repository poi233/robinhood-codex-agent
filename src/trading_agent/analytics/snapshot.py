from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_agent.core.io import read_json, write_json
from trading_agent.core.time import pt_date_string


def _history_dir(agent_root: Path, date: str) -> Path:
    return agent_root / "runtime" / "analytics" / "history" / date


def _analytics_dir(agent_root: Path) -> Path:
    return agent_root / "runtime" / "analytics"


# The "latest" reports the snapshot archives a dated copy of. Missing ones are skipped (best-effort).
_SNAPSHOT_FILES = (
    "calibration_report.json",
    "calibration_report.md",
    "fill_quality_report.json",
    "ai_signal_study.json",
    "ai_ablation.json",
    "growth_observations.json",
    "experiment_report.json",
    "promotion_recommendation.md",
    "weight_suggestion.json",
)


def _top_component_ic(calibration: dict[str, Any]) -> dict[str, Any]:
    """Per-horizon highest-|IC| component from the calibration attribution block."""
    out: dict[str, Any] = {}
    for horizon, rows in (calibration.get("attribution") or {}).items():
        best = None
        for row in rows:
            ic = row.get("ic")
            if ic is None:
                continue
            if best is None or abs(ic) > abs(best["ic"]):
                best = {"component": row.get("component"), "ic": ic}
        if best is not None:
            out[str(horizon)] = best
    return out


def build_nightly_summary(agent_root: Path, date: str) -> dict[str, Any]:
    """Small, stable headline schema for one night — the data source I3 trends aggregate over.
    Pure read of already-written artifacts; absent inputs degrade to None/0, never crash."""
    from trading_agent.growth.experiment_queue import list_experiments
    from trading_agent.growth.proposals import default_proposals_dir
    from trading_agent.replay.analysis import build_replay_report

    analytics = _analytics_dir(agent_root)

    def _read(name: str) -> dict[str, Any]:
        path = analytics / name
        if not path.exists():
            return {}
        payload = read_json(path)
        return payload if isinstance(payload, dict) else {}

    replay = build_replay_report(agent_root)
    fill = replay.get("fill_rate") or {}
    blocked = replay.get("blocked_reasons") or {}
    calibration = _read("calibration_report.json")
    experiment = _read("experiment_report.json")

    try:
        active_shadow = len(list_experiments(agent_root, status="active_shadow"))
    except Exception:
        active_shadow = 0

    proposals_dir = default_proposals_dir(agent_root, date)
    proposal_count = len(list(proposals_dir.glob("proposal_*.json"))) if proposals_dir.exists() else 0

    challengers = []
    for ch in (experiment.get("challengers") or []):
        metrics = ch.get("metrics") or {}
        challengers.append({
            "challenger_strategy_id": ch.get("challenger_strategy_id"),
            "fill_rate_pct": metrics.get("fill_rate_pct"),
            "no_trade_rate_pct": metrics.get("no_trade_rate_pct"),
            "max_drawdown": metrics.get("max_drawdown"),
            "realized_pnl": metrics.get("realized_pnl"),
        })

    return {
        "date": date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": 1,
        "fill_rate_pct": fill.get("fill_rate_pct"),
        "no_trade_rate_pct": blocked.get("no_trade_rate_pct"),
        "run_date_count": calibration.get("run_date_count"),
        "calibration_sample_size": calibration.get("sample_size"),
        "top_component_ic": _top_component_ic(calibration),
        "proposal_count": proposal_count,
        "active_shadow_count": active_shadow,
        "champion": (experiment.get("champion") or None),
        "challengers": challengers,
    }


def write_analysis_snapshot(agent_root: Path, *, date: str | None = None) -> Path:
    """Archive a dated copy of the night's key reports into history/<date>/ plus a nightly_summary.json.
    Idempotent: re-running for the same date overwrites that day's snapshot. Additive — never touches
    the "latest" reports under runtime/analytics/."""
    resolved = date or pt_date_string()
    analytics = _analytics_dir(agent_root)
    dest = _history_dir(agent_root, resolved)
    dest.mkdir(parents=True, exist_ok=True)

    for name in _SNAPSHOT_FILES:
        src = analytics / name
        if src.exists():
            shutil.copy2(src, dest / name)

    summary = build_nightly_summary(agent_root, resolved)
    write_json(dest / "nightly_summary.json", summary)
    return dest
