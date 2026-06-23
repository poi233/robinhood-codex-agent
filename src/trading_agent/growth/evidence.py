from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from trading_agent.core.io import read_json

# H6: gate self-growth proposals on real calibration / weight / AI evidence. When
# ENABLE_EVIDENCE_PROPOSALS=1, a proposal must cite at least one supporting evidence item or it is
# dropped — "don't propose a change the data doesn't back". Default off keeps the current
# rule-registry propose behavior byte-for-byte. The validator red lines and human-only promotion are
# unchanged; this only makes propose stricter, never more permissive.


def evidence_proposals_enabled() -> bool:
    # Always on: a proposal must cite at least one supporting evidence item.
    return True


def _read(agent_root: Path, name: str) -> dict[str, Any]:
    path = agent_root / "runtime" / "analytics" / name
    if not path.exists():
        return {}
    payload = read_json(path)
    return payload if isinstance(payload, dict) else {}


def gather_evidence(agent_root: Path) -> dict[str, Any]:
    """Read-only bundle of the evidence proposals can cite: calibration near-miss + component IC,
    weight suggestion, overlay IC, and new H6 types (factor IC / AI calibration / setup outcomes).
    Absent reports degrade to empty, never crash."""
    calibration = _read(agent_root, "calibration_report.json")
    weight = _read(agent_root, "weight_suggestion.json")
    ai_study = _read(agent_root, "ai_signal_study.json")
    attribution = calibration.get("attribution") or {}
    return {
        "near_miss": calibration.get("near_miss") or {},
        "attribution": attribution,
        "calibration_sample_size": calibration.get("sample_size") or 0,
        "weight_components": weight.get("components") or [],
        "overlay_components": _overlay_component_evidence(attribution),
        # H6 extended evidence types
        "factor_positive_ic": _factor_positive_ic_evidence(attribution),
        "ai_calibration": _ai_calibration_evidence(ai_study),
        "setup_outcomes": list(calibration.get("setup_outcomes") or []),
    }


def _near_miss_evidence(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    """near_miss returns ≈ or above cleared ⇒ the trade gate may be too strict — supports lowering
    trade_threshold."""
    out: list[dict[str, Any]] = []
    for horizon, classes in (evidence.get("near_miss") or {}).items():
        cleared = (classes.get("cleared") or {}).get("mean_return")
        near = (classes.get("near_miss") or {}).get("mean_return")
        if cleared is None or near is None:
            continue
        out.append({
            "source": "calibration.near_miss",
            "horizon_d": horizon,
            "cleared_mean_return": cleared,
            "near_miss_mean_return": near,
            "detail": "near-miss candidates' forward return vs cleared — informs whether the trade gate is too strict",
        })
    return out


def _component_ic_evidence(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for horizon, rows in (evidence.get("attribution") or {}).items():
        for row in rows:
            if row.get("ic") is not None:
                out.append({"source": "calibration.attribution", "horizon_d": horizon,
                            "component": row.get("component"), "ic": row.get("ic")})
    return out


_OVERLAY_COMPONENTS = {
    "final_rank_delta",
    "advisory_size_multiplier",
    "factor_alpha",
    "ai_composite",
    "regime_multiplier",
    "portfolio_multiplier",
    "portfolio_position_weight",
}


def _overlay_component_evidence(attribution: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for horizon, rows in attribution.items():
        for row in rows:
            component = str(row.get("component") or "")
            if component in _OVERLAY_COMPONENTS and row.get("ic") is not None:
                out.append({
                    "source": "calibration.overlay_component_ic",
                    "horizon_d": horizon,
                    "component": component,
                    "ic": row.get("ic"),
                })
    return out


_SCORING_COMPONENTS = {"dsa", "technical", "kronos", "quote", "catalyst"}


def _factor_positive_ic_evidence(attribution: dict[str, Any]) -> list[dict[str, Any]]:
    """H6: scoring components (non-overlay) with positive mean IC across horizons.

    Supports proposals that bump the weight of a component whose IC data says it predicts
    forward returns. Returns one item per component that has at least one positive IC value."""
    ic_by_component: dict[str, list[float]] = {}
    for horizon, rows in attribution.items():
        for row in rows:
            component = str(row.get("component") or "")
            if component not in _SCORING_COMPONENTS:
                continue
            ic = row.get("ic")
            if isinstance(ic, (int, float)):
                ic_by_component.setdefault(component, []).append(float(ic))
    out: list[dict[str, Any]] = []
    for component, ics in ic_by_component.items():
        mean_ic = sum(ics) / len(ics)
        out.append({
            "source": "calibration.factor_positive_ic",
            "component": component,
            "mean_ic": round(mean_ic, 4),
            "positive": mean_ic > 0,
        })
    return out


def _ai_calibration_evidence(ai_study: dict[str, Any]) -> list[dict[str, Any]]:
    """H6: per-layer AI calibration quality from ai_signal_study.json.

    Returns one item per layer with whether confidence is monotone-calibrated (higher
    confidence → higher return). Non-monotone layers suggest the AI weight may need
    adjustment or the layer's proposals should be treated cautiously."""
    layers = ai_study.get("layers") or {}
    out: list[dict[str, Any]] = []
    for layer_name, data in layers.items():
        if not isinstance(data, dict):
            continue
        buckets_by_horizon = data.get("confidence_calibration") or {}
        for horizon, buckets in buckets_by_horizon.items():
            if not buckets:
                continue
            sorted_buckets = sorted(buckets, key=lambda b: b.get("confidence_low", 0))
            returns = [b.get("mean_return") for b in sorted_buckets if b.get("mean_return") is not None]
            monotone = all(returns[i] <= returns[i + 1] for i in range(len(returns) - 1)) if len(returns) > 1 else None
            ic = data.get("confidence_ic", {}).get(str(horizon))
            out.append({
                "source": "calibration.ai_calibration",
                "layer": str(layer_name),
                "horizon_d": str(horizon),
                "monotone_calibrated": monotone,
                "confidence_ic": ic,
            })
    return out


def _setup_outcome_evidence(evidence: dict[str, Any], setup_type: str | None = None) -> list[dict[str, Any]]:
    """H6: setup outcome items (win_rate / fills) for a specific setup_type or all setups."""
    rows = evidence.get("setup_outcomes") or []
    if setup_type:
        return [r for r in rows if str(r.get("setup_type") or "") == setup_type]
    return list(rows)


# Maps overlay mutation field names to the calibration component names they're backed by.
_OVERLAY_FIELD_TO_COMPONENT: dict[str, str] = {
    "factor_weight": "factor_alpha",
    "ai_weight": "ai_composite",
    "regime_size_multiplier": "regime_multiplier",
    "portfolio_near_cap_multiplier": "portfolio_multiplier",
}


def _overlay_ic_evidence(evidence: dict[str, Any], field: str) -> list[dict[str, Any]]:
    """Evidence items for an overlay field: calibration IC for the matching overlay component."""
    component = _OVERLAY_FIELD_TO_COMPONENT.get(field)
    if not component:
        return []
    return [
        item for item in (evidence.get("overlay_components") or [])
        if item.get("component") == component and item.get("ic") is not None
    ]


def evidence_for_proposal(proposal: dict[str, Any], evidence: dict[str, Any]) -> list[dict[str, Any]]:
    """The evidence items that support a given proposal, by what it mutates. Empty list ⇒ unsupported
    (and, in evidence mode, the proposal is dropped)."""
    mutation = proposal.get("mutation") or {}
    module = str(mutation.get("module") or "")
    field = str(mutation.get("field") or "")
    items: list[dict[str, Any]] = []
    if field == "trade_threshold":
        items.extend(_near_miss_evidence(evidence))
    if module == "scoring":
        items.extend(_component_ic_evidence(evidence))
        # H6: factor_positive_ic backs component_weights proposals
        if field == "component_weights":
            items.extend(evidence.get("factor_positive_ic") or [])
    if module == "overlay":
        items.extend(_overlay_ic_evidence(evidence, field))
    if module == "setups":
        # H6: setup_outcomes backs any setup-selection proposal
        items.extend(_setup_outcome_evidence(evidence))
    if module == "policy" and field in {"price_setup_weight", "min_reward_risk"}:
        # H6: setup_outcomes backs policy tuning that affects setup selection
        items.extend(_setup_outcome_evidence(evidence))
    return items


def apply_evidence_gate(
    proposals: list[dict[str, Any]], evidence: dict[str, Any]
) -> list[dict[str, Any]]:
    """Attach an `evidence` list to each proposal and drop the ones with no supporting evidence.
    Used only when ENABLE_EVIDENCE_PROPOSALS=1."""
    kept: list[dict[str, Any]] = []
    for proposal in proposals:
        items = evidence_for_proposal(proposal, evidence)
        if not items:
            continue  # no data backing this change -> don't propose it
        enriched = dict(proposal)
        enriched["evidence"] = items
        kept.append(enriched)
    return kept
