from __future__ import annotations

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import read_json
from trading_agent.growth.observations import GrowthContext, Observation


def diagnose(ctx: GrowthContext) -> list[Observation]:
    flagged: list[str] = []
    for run_date in ctx.run_dates:
        path = build_runtime_paths(ctx.agent_root, run_date=run_date).premarket_diagnostics_path
        if not path.exists():
            continue
        payload = read_json(path)
        if not isinstance(payload, dict):
            continue
        warnings = payload.get("warnings") or []
        if any(
            str(w).startswith(("theme_concentration_exceeded", "speculative_concentration_exceeded"))
            for w in warnings
        ):
            flagged.append(run_date)
    if not flagged:
        return []
    return [
        Observation(
            "recurring_theme_concentration", "scoring", "info",
            {"run_dates": flagged, "count": len(flagged)},
            "Theme/speculative caps repeatedly exceeded; consider a watchlist-cap experiment (paper).",
        )
    ]
