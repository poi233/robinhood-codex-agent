from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from trading_agent.core.io import write_json
from trading_agent.core.time import pt_date_string
from trading_agent.growth.observations import build_growth_observations
from trading_agent.growth.policy import load_growth_policy
from trading_agent.growth.validator import validate_mutation

_EPS = 1e-9

# A proposal rule inspects the flattened observation list and emits zero or more
# candidate mutations on whitelisted config fields. Add a rule by registering it here;
# every emitted mutation is still run through validate_mutation, so a rule can never
# produce a proposal that escapes the growth_policy safety boundary.
ProposalRule = Callable[[list[dict[str, Any]], dict[str, Any], dict[tuple[str, str], float], str], list[dict[str, Any]]]

# M5: Evidence-based rules use calibration IC (not observations) to suggest overlay tuning.
EvidenceProposalRule = Callable[[dict[str, Any], dict[str, Any], dict[tuple[str, str], float], str], list[dict[str, Any]]]

# Current overlay weights default to 0.0 — not yet wired in the live overlay code. Proposals
# suggest bumping them toward their max once positive IC is observed. A human must review,
# approve, and ultimately wire the weights before they take effect.
_OVERLAY_DEFAULTS: dict[tuple[str, str], float] = {
    ("overlay", "factor_weight"): 0.0,
    ("overlay", "ai_weight"): 0.0,
}


def _threshold_step(
    module: str,
    field: str,
    policy: dict[str, Any],
    current: dict[tuple[str, str], float],
    *,
    direction: int,
    based_on: str,
    rationale: str,
    run_date: str,
) -> dict[str, Any] | None:
    """Propose moving one whitelisted threshold by exactly one max_delta step.

    Returns None (no proposal) when the field is unknown, the value is already at the
    clamped bound (a no-op), or the resulting mutation fails validation — fail-closed.
    """
    spec = ((policy.get("allowed_mutations") or {}).get(module) or {}).get(field)
    if not isinstance(spec, dict):
        return None
    cur = current.get((module, field))
    if cur is None:
        return None
    step = float(spec.get("max_delta", 0.0))
    proposed = cur + direction * step
    proposed = max(float(spec["min"]), min(float(spec["max"]), proposed))
    if abs(proposed - cur) < _EPS:
        return None  # already at bound: nothing to change
    mutation = {"module": module, "field": field, "current": cur, "proposed": round(proposed, 4)}
    ok, violations = validate_mutation(mutation, policy)
    if not ok:
        return None  # never emit a proposal that escapes the safety boundary
    return {
        "proposal_id": f"{run_date}_{module}_{field}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "based_on_observation": based_on,
        "mutation": mutation,
        "rationale": rationale,
        "validation": {"ok": ok, "violations": violations},
        "status": "proposed",
    }


def _rule_rarely_trades(
    observations: list[dict[str, Any]],
    policy: dict[str, Any],
    current: dict[tuple[str, str], float],
    run_date: str,
) -> list[dict[str, Any]]:
    triggers = {"low_trade_frequency", "high_no_trade_rate"}
    hit = next((o for o in observations if o.get("type") in triggers), None)
    if hit is None:
        return []
    proposal = _threshold_step(
        "scoring", "trade_threshold", policy, current,
        direction=-1,
        based_on=str(hit.get("type")),
        rationale=(
            "System rarely fills / mostly no-trades; lower the trade threshold by one "
            "bounded step so more candidates clear the gate. Paper-only experiment."
        ),
        run_date=run_date,
    )
    return [proposal] if proposal else []


def _rule_theme_concentration(
    observations: list[dict[str, Any]],
    policy: dict[str, Any],
    current: dict[tuple[str, str], float],
    run_date: str,
) -> list[dict[str, Any]]:
    hit = next((o for o in observations if o.get("type") == "recurring_theme_concentration"), None)
    if hit is None:
        return []
    proposal = _threshold_step(
        "scoring", "watchlist_threshold", policy, current,
        direction=1,
        based_on="recurring_theme_concentration",
        rationale=(
            "Theme/speculative caps repeatedly exceeded; raise the watchlist threshold by one "
            "bounded step so fewer marginal theme names enter the watchlist. Paper-only experiment."
        ),
        run_date=run_date,
    )
    return [proposal] if proposal else []


PROPOSAL_RULES: list[ProposalRule] = [
    _rule_rarely_trades,
    _rule_theme_concentration,
]


def _mean_overlay_ic(evidence: dict[str, Any], component: str) -> float | None:
    """Mean IC across all horizons for a given overlay component. None if no data."""
    from trading_agent.growth.evidence import _overlay_ic_evidence, _OVERLAY_FIELD_TO_COMPONENT

    # Reverse-map component name → field name to reuse _overlay_ic_evidence
    field = next((f for f, c in _OVERLAY_FIELD_TO_COMPONENT.items() if c == component), None)
    if not field:
        return None
    items = _overlay_ic_evidence(evidence, field)
    ics = [i["ic"] for i in items if isinstance(i.get("ic"), (int, float))]
    return sum(ics) / len(ics) if ics else None


def _rule_overlay_factor_positive_ic(
    evidence: dict[str, Any],
    policy: dict[str, Any],
    current: dict[tuple[str, str], float],
    run_date: str,
) -> list[dict[str, Any]]:
    """If factor_alpha overlay has positive mean IC, propose incrementing overlay.factor_weight."""
    ic = _mean_overlay_ic(evidence, "factor_alpha")
    if ic is None or ic <= 0:
        return []
    proposal = _threshold_step(
        "overlay", "factor_weight", policy, current,
        direction=1,
        based_on="overlay_factor_alpha_positive_ic",
        rationale=(
            f"factor_alpha overlay component shows positive mean IC ({ic:+.3f}) across calibration "
            "horizons; bump overlay.factor_weight by one bounded step to give factor signals more "
            "influence on intraday ranking. Paper-only experiment."
        ),
        run_date=run_date,
    )
    return [proposal] if proposal else []


def _rule_overlay_ai_positive_ic(
    evidence: dict[str, Any],
    policy: dict[str, Any],
    current: dict[tuple[str, str], float],
    run_date: str,
) -> list[dict[str, Any]]:
    """If ai_composite overlay has positive mean IC, propose incrementing overlay.ai_weight."""
    ic = _mean_overlay_ic(evidence, "ai_composite")
    if ic is None or ic <= 0:
        return []
    proposal = _threshold_step(
        "overlay", "ai_weight", policy, current,
        direction=1,
        based_on="overlay_ai_composite_positive_ic",
        rationale=(
            f"ai_composite overlay component shows positive mean IC ({ic:+.3f}) across calibration "
            "horizons; bump overlay.ai_weight by one bounded step to give AI signal confidence "
            "more influence on intraday ranking. Paper-only experiment."
        ),
        run_date=run_date,
    )
    return [proposal] if proposal else []


EVIDENCE_RULES: list[EvidenceProposalRule] = [
    _rule_overlay_factor_positive_ic,
    _rule_overlay_ai_positive_ic,
]


def evidence_proposals(
    evidence: dict[str, Any],
    policy: dict[str, Any],
    current: dict[tuple[str, str], float],
    *,
    run_date: str,
) -> list[dict[str, Any]]:
    """M5: Generate proposals from calibration IC evidence (not observations).

    These rules fire when overlay components show positive IC, suggesting the overlay is
    helping and its weight should be increased. All proposals are still bounded by the
    growth_policy whitelist and require human approval before any shadow run.
    """
    proposals: list[dict[str, Any]] = []
    for rule in EVIDENCE_RULES:
        proposals.extend(rule(evidence, policy, current, run_date))
    return proposals


def proposals_from_observations(
    observations: list[dict[str, Any]],
    policy: dict[str, Any],
    current: dict[tuple[str, str], float],
    *,
    run_date: str,
) -> list[dict[str, Any]]:
    """Pure: turn observations into validated, whitelist-only strategy proposals.

    Never auto-enables anything; returns proposal dicts only. The per-run count is
    capped by growth_policy.proposal.max_new_proposals_per_week (full cross-run
    frequency enforcement is the experiment queue's job in G5).
    """
    proposals: list[dict[str, Any]] = []
    for rule in PROPOSAL_RULES:
        proposals.extend(rule(observations, policy, current, run_date))
    cap = int((policy.get("proposal") or {}).get("max_new_proposals_per_week", len(proposals)) or len(proposals))
    return proposals[:cap]


def _current_values(agent_root: Path) -> dict[tuple[str, str], float]:
    from trading_agent.planner.scoring_profiles import load_scoring_profile

    profile = load_scoring_profile(agent_root / "src" / "config")
    values: dict[tuple[str, str], float] = {
        ("scoring", "trade_threshold"): float(profile["trade_threshold"]),
        ("scoring", "watchlist_threshold"): float(profile["watchlist_threshold"]),
    }
    values.update(_OVERLAY_DEFAULTS)
    return values


def _flatten_observations(payload: dict[str, Any]) -> list[dict[str, Any]]:
    flat: list[dict[str, Any]] = list(payload.get("global") or [])
    for module_obs in (payload.get("modules") or {}).values():
        flat.extend(module_obs or [])
    return flat


def build_proposals(
    agent_root: Path,
    *,
    run_date: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> list[dict[str, Any]]:
    resolved_run_date = run_date or pt_date_string()
    payload = build_growth_observations(agent_root, since=since, until=until)
    observations = _flatten_observations(payload)
    policy = load_growth_policy(agent_root)
    current = _current_values(agent_root)
    proposals = proposals_from_observations(observations, policy, current, run_date=resolved_run_date)

    # H6 (ENABLE_EVIDENCE_PROPOSALS): require calibration/weight evidence — attach it and drop
    # proposals the data doesn't back. Default off => current behavior unchanged.
    # M5: also run evidence-based overlay rules whenever evidence is available.
    from trading_agent.growth.evidence import apply_evidence_gate, evidence_proposals_enabled, gather_evidence

    evidence_bundle = gather_evidence(agent_root)
    # M5: evidence-based overlay rules (factor/ai IC → weight proposals). Always run; the gate
    # below then filters by data quality when ENABLE_EVIDENCE_PROPOSALS=1.
    proposals.extend(evidence_proposals(evidence_bundle, policy, current, run_date=resolved_run_date))

    if evidence_proposals_enabled():
        proposals = apply_evidence_gate(proposals, evidence_bundle)
    return proposals


def default_proposals_dir(agent_root: Path, run_date: str) -> Path:
    return agent_root / "runtime" / "strategy_proposals" / run_date


def _proposal_markdown(proposal: dict[str, Any]) -> str:
    mutation = proposal["mutation"]
    lines = [
        f"# Strategy Proposal — {proposal['proposal_id']}",
        "",
        f"- Status: **{proposal['status']}** (paper-only experiment; not enabled)",
        f"- Based on observation: `{proposal['based_on_observation']}`",
        f"- Generated at: {proposal['generated_at']}",
        "",
        "## Proposed mutation",
        "",
        f"- Module / field: `{mutation['module']}.{mutation['field']}`",
        f"- Current: `{mutation['current']}`  →  Proposed: `{mutation['proposed']}`",
        "",
        "## Rationale",
        "",
        proposal["rationale"],
        "",
        "## Validation",
        "",
        f"- ok: `{proposal['validation']['ok']}`",
        f"- violations: `{proposal['validation']['violations']}`",
        "",
        "> This proposal changes no champion configuration. A human must review and approve "
        "any experiment before it can run in shadow paper (see roadmap G4–G8).",
        "",
    ]
    return "\n".join(lines)


def write_proposals(
    agent_root: Path,
    *,
    run_date: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> list[Path]:
    """Generate proposals and write each as a .json + .md under runtime/strategy_proposals/<date>/.

    Returns the written .json paths. Touches nothing under src/config or any trading ledger.
    """
    resolved_run_date = run_date or pt_date_string()
    proposals = build_proposals(agent_root, run_date=resolved_run_date, since=since, until=until)
    out_dir = default_proposals_dir(agent_root, resolved_run_date)
    written: list[Path] = []
    for index, proposal in enumerate(proposals, start=1):
        stem = f"proposal_{index:03d}_{proposal['mutation']['module']}_{proposal['mutation']['field']}"
        json_path = out_dir / f"{stem}.json"
        write_json(json_path, proposal)
        (out_dir / f"{stem}.md").write_text(_proposal_markdown(proposal), encoding="utf-8")
        written.append(json_path)
    return written
