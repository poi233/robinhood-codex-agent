from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_agent.core.io import read_json, write_json

# Scalar headline metrics lifted straight from each nightly_summary.json into a per-date series.
_SCALAR_METRICS = (
    "fill_rate_pct",
    "no_trade_rate_pct",
    "proposal_count",
    "active_shadow_count",
    "calibration_sample_size",
    "run_date_count",
)


def _history_root(agent_root: Path) -> Path:
    return agent_root / "runtime" / "analytics" / "history"


def _load_snapshots(agent_root: Path, *, since: str | None, until: str | None) -> list[dict[str, Any]]:
    root = _history_root(agent_root)
    if not root.exists():
        return []
    snapshots: list[dict[str, Any]] = []
    for day_dir in sorted(root.iterdir()):
        if not day_dir.is_dir():
            continue
        date = day_dir.name
        if since and date < since:
            continue
        if until and date > until:
            continue
        path = day_dir / "nightly_summary.json"
        if not path.exists():
            continue
        payload = read_json(path)
        if isinstance(payload, dict):
            payload.setdefault("date", date)
            snapshots.append(payload)
    snapshots.sort(key=lambda s: str(s.get("date")))
    return snapshots


def build_trend(agent_root: Path, *, since: str | None = None, until: str | None = None) -> dict[str, Any]:
    """Aggregate the per-day nightly_summary.json snapshots (I2) into per-metric time series. One
    place that computes the trend, reused by the CLI and the dashboard (I4). Returns
    `status: insufficient_data` (not an error) when there are no snapshots yet."""
    snapshots = _load_snapshots(agent_root, since=since, until=until)
    if not snapshots:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "insufficient_data",
            "snapshot_count": 0,
            "dates": [],
            "series": {},
        }

    dates = [str(s.get("date")) for s in snapshots]
    series: dict[str, list[dict[str, Any]]] = {}

    for metric in _SCALAR_METRICS:
        points = [{"date": str(s.get("date")), "value": s.get(metric)} for s in snapshots if s.get(metric) is not None]
        if points:
            series[metric] = points

    # Per-horizon top component IC: one series per horizon seen in any snapshot.
    horizons: set[str] = set()
    for s in snapshots:
        horizons.update((s.get("top_component_ic") or {}).keys())
    for h in sorted(horizons):
        points = []
        for s in snapshots:
            entry = (s.get("top_component_ic") or {}).get(h)
            if entry and entry.get("ic") is not None:
                points.append({"date": str(s.get("date")), "component": entry.get("component"), "value": entry.get("ic")})
        if points:
            series[f"top_component_ic_{h}d"] = points

    # Champion fill / no-trade trend.
    champ_points = []
    for s in snapshots:
        champ = s.get("champion") or {}
        if champ.get("fill_rate_pct") is not None:
            champ_points.append({"date": str(s.get("date")), "value": champ.get("fill_rate_pct")})
    if champ_points:
        series["champion_fill_rate_pct"] = champ_points

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ok",
        "snapshot_count": len(snapshots),
        "dates": dates,
        "series": series,
    }


def default_trend_path(agent_root: Path) -> Path:
    return agent_root / "runtime" / "analytics" / "trend.json"


def write_trend(agent_root: Path, *, since: str | None = None, until: str | None = None, output: Path | None = None) -> Path:
    trend = build_trend(agent_root, since=since, until=until)
    out = output or default_trend_path(agent_root)
    write_json(out, trend)
    return out
