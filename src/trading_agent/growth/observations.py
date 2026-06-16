from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import write_json
from trading_agent.replay.analysis import build_replay_report, discover_run_dates

# Thresholds. Kept module-level (not in growth_policy.json) because they tune the
# *diagnostics*, not any trading parameter; promoting them to config is a later option.
LOW_TRADE_FREQUENCY_PER_DAY = 0.25
HIGH_NO_TRADE_RATE_PCT = 80.0
DOMINANT_BLOCKED_REASON_PCT = 50.0
HIGH_PENDING_CANCEL_RATE_PCT = 50.0


@dataclass
class Observation:
    type: str
    module: str
    severity: str  # "info" | "warning" | "critical"
    evidence: dict[str, Any]
    suggested_action: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GrowthContext:
    agent_root: Path
    run_dates: list[str]
    replay: dict[str, Any]


def build_growth_context(agent_root: Path, *, since: str | None = None, until: str | None = None) -> GrowthContext:
    """Compute the shared, relatively expensive inputs once for all diagnosers."""
    run_dates = discover_run_dates(agent_root, since_date=since, until_date=until)
    replay = build_replay_report(agent_root, since_date=since, until_date=until)
    return GrowthContext(agent_root=agent_root, run_dates=run_dates, replay=replay)


def global_observations(ctx: GrowthContext) -> list[Observation]:
    obs: list[Observation] = []
    fr = ctx.replay.get("fill_rate") or {}
    br = ctx.replay.get("blocked_reasons") or {}
    n_days = max(len(ctx.run_dates), 1)

    filled = int(fr.get("filled") or 0)
    per_day = filled / n_days
    if ctx.run_dates and per_day < LOW_TRADE_FREQUENCY_PER_DAY:
        obs.append(Observation(
            "low_trade_frequency", "global", "warning",
            {"filled": filled, "run_days": n_days, "fills_per_day": round(per_day, 3)},
            "System rarely fills; review entry thresholds / watchlist breadth (paper experiment).",
        ))

    no_trade_rate = float(br.get("no_trade_rate_pct") or 0.0)
    if int(br.get("total_evaluations") or 0) > 0 and no_trade_rate >= HIGH_NO_TRADE_RATE_PCT:
        obs.append(Observation(
            "high_no_trade_rate", "global", "warning",
            {"no_trade_rate_pct": no_trade_rate, "total_evaluations": br.get("total_evaluations")},
            "Most evaluations end in no-trade; inspect dominant blocked reason.",
        ))

    reason_counts = br.get("reason_counts") or {}
    total_reasons = sum(int(v) for v in reason_counts.values())
    if total_reasons > 0:
        top_reason, top_count = max(reason_counts.items(), key=lambda kv: int(kv[1]))
        pct = top_count / total_reasons * 100
        if pct >= DOMINANT_BLOCKED_REASON_PCT:
            obs.append(Observation(
                "dominant_blocked_reason", "global", "info",
                {"reason": top_reason, "count": int(top_count), "pct": round(pct, 1)},
                f"{round(pct, 1)}% of no-trades are {top_reason!r}; target that gate for tuning.",
            ))

    canceled = int(fr.get("canceled") or 0)
    total_orders = int(fr.get("total_orders") or 0)
    if total_orders > 0:
        cancel_rate = canceled / total_orders * 100
        if cancel_rate >= HIGH_PENDING_CANCEL_RATE_PCT:
            obs.append(Observation(
                "high_pending_cancel_rate", "paper", "warning",
                {"canceled": canceled, "total_orders": total_orders, "cancel_rate_pct": round(cancel_rate, 1)},
                "Many limits never fill before day-end cancel; review entry-zone / chase tolerance.",
            ))

    missing = [
        d for d in ctx.run_dates
        if not (build_runtime_paths(ctx.agent_root, run_date=d).run_state_dir / "run_manifest.json").exists()
    ]
    if missing:
        obs.append(Observation(
            "missing_manifest", "global", "warning",
            {"run_dates_without_manifest": missing, "count": len(missing)},
            "These runs are not traceable to a strategy version; ensure run_manifest is written.",
        ))
    return obs


def build_growth_observations(agent_root: Path, *, since: str | None = None, until: str | None = None) -> dict[str, Any]:
    ctx = build_growth_context(agent_root, since=since, until=until)
    # Lazy import avoids a package import cycle (diagnosers import this module).
    from trading_agent.growth.diagnosers import run_all

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_date_range": {"since": since, "until": until},
        "run_date_count": len(ctx.run_dates),
        "global": [o.to_dict() for o in global_observations(ctx)],
        "modules": run_all(ctx),
    }


def default_growth_observations_path(agent_root: Path) -> Path:
    return agent_root / "runtime" / "analytics" / "growth_observations.json"


def write_growth_observations(agent_root: Path, *, since: str | None = None, until: str | None = None) -> Path:
    payload = build_growth_observations(agent_root, since=since, until=until)
    path = default_growth_observations_path(agent_root)
    write_json(path, payload)
    return path
