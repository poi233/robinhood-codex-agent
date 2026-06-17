from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_agent.core.io import read_json, write_json

# E2: turn the E1 calibration IC evidence into a *suggested* re-weighting of the scoring components.
# HARD RED LINE: this only PROPOSES weights. It never writes scoring.WEIGHTS or any profile. Applying
# a new weight set is a manual step — register it as a new strategy version (B2) and run it as a
# shadow challenger (G6) first. "Compute a data-backed suggestion" != "auto-change the strategy".


def current_component_weights() -> dict[str, float]:
    """The champion scoring component weights the suggestion is measured against."""
    from trading_agent.planner.scoring import WEIGHTS

    return dict(WEIGHTS)


def _component_ic(calibration: dict[str, Any], horizon: str, components: list[str]) -> dict[str, float | None]:
    """Per-component IC at `horizon` from the calibration attribution block, for the given components."""
    rows = (calibration.get("attribution") or {}).get(horizon) or []
    by_name = {row.get("component"): row.get("ic") for row in rows}
    return {c: by_name.get(c) for c in components}


def suggest_weights(
    calibration: dict[str, Any],
    current_weights: dict[str, float],
    *,
    horizon: str,
    damping: float = 0.5,
) -> dict[str, Any]:
    """Suggest a re-weighting tilted toward components with higher forward-return IC.

    Each component's positive IC (max(0, IC)) is normalized across components; a component above the
    mean positive IC is nudged up, below the mean nudged down, scaled by `damping` (0 = no change,
    1 = full tilt). Weights are renormalized to sum to 1. Components with no IC keep their prior.
    Returns `status: insufficient_data` (weights unchanged) when no component has a usable IC."""
    components = list(current_weights)
    ics = _component_ic(calibration, horizon, components)
    usable = {c: ic for c, ic in ics.items() if isinstance(ic, (int, float))}
    if not usable:
        return {
            "status": "insufficient_data",
            "horizon": horizon,
            "reason": "no component IC available at this horizon yet (run analytics calibrate with enough run dates)",
            "current_weights": current_weights,
            "suggested_weights": dict(current_weights),
            "components": [],
        }

    pos = {c: max(0.0, ics.get(c) or 0.0) for c in components}
    max_pos = max(pos.values())
    norm = {c: (pos[c] / max_pos if max_pos > 0 else 0.0) for c in components}
    mean_norm = sum(norm.values()) / len(norm)

    raw: dict[str, float] = {}
    for c in components:
        multiplier = 1.0 + damping * (norm[c] - mean_norm)
        raw[c] = max(0.0, current_weights[c] * multiplier)
    total = sum(raw.values()) or 1.0
    suggested = {c: round(raw[c] / total, 4) for c in components}

    rows = []
    for c in components:
        rows.append({
            "component": c,
            "ic": ics.get(c),
            "current_weight": current_weights[c],
            "suggested_weight": suggested[c],
            "delta": round(suggested[c] - current_weights[c], 4),
        })
    rows.sort(key=lambda r: (r["ic"] is not None, r["ic"] if r["ic"] is not None else -1.0), reverse=True)

    return {
        "status": "ok",
        "horizon": horizon,
        "damping": damping,
        "current_weights": current_weights,
        "suggested_weights": suggested,
        "components": rows,
    }


def build_weight_suggestion_report(agent_root: Path, *, horizon: str | None = None, damping: float = 0.5) -> dict[str, Any]:
    """Read the E1 calibration_report and produce a weight-suggestion report. Read-only."""
    from trading_agent.replay.calibration import default_calibration_report_path

    calibration = read_json(default_calibration_report_path(agent_root)) if default_calibration_report_path(agent_root).exists() else {}
    if not isinstance(calibration, dict):
        calibration = {}
    horizons = [str(h) for h in (calibration.get("horizons") or [])]
    resolved_h = horizon or (horizons[0] if horizons else "1")
    suggestion = suggest_weights(calibration, current_component_weights(), horizon=resolved_h, damping=damping)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "calibration_generated_at": calibration.get("generated_at"),
        "calibration_sample_size": calibration.get("sample_size"),
        "disclaimer": "Suggestion only — never auto-applied. To adopt, register a new strategy version "
                      "(B2) and run it as a shadow challenger (G6) before any human promotion (G8).",
        **suggestion,
    }


def default_weight_suggestion_path(agent_root: Path) -> Path:
    return agent_root / "runtime" / "analytics" / "weight_suggestion.json"


def write_weight_suggestion_report(agent_root: Path, *, horizon: str | None = None, damping: float = 0.5) -> Path:
    report = build_weight_suggestion_report(agent_root, horizon=horizon, damping=damping)
    out = default_weight_suggestion_path(agent_root)
    write_json(out, report)
    return out
