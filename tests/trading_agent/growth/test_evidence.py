from __future__ import annotations

from trading_agent.growth.evidence import apply_evidence_gate, evidence_for_proposal, gather_evidence


_EVIDENCE = {
    "near_miss": {"5": {"cleared": {"mean_return": 0.02}, "near_miss": {"mean_return": 0.018}}},
    "attribution": {"1": [{"component": "technical", "ic": 0.2}]},
    "calibration_sample_size": 12,
    "weight_components": [],
}


def _proposal(module: str, field: str) -> dict:
    return {"proposal_id": f"x_{module}_{field}", "mutation": {"module": module, "field": field, "current": 50.0, "proposed": 48.0}}


def test_trade_threshold_proposal_is_supported_by_near_miss():
    items = evidence_for_proposal(_proposal("scoring", "trade_threshold"), _EVIDENCE)
    assert any(i["source"] == "calibration.near_miss" for i in items)


def test_unsupported_proposal_has_no_evidence():
    # A field with no near-miss / scoring-IC link gets no evidence.
    items = evidence_for_proposal(_proposal("risk_overlay", "max_theme_pct"), _EVIDENCE)
    assert items == []


def test_gate_drops_unsupported_and_attaches_evidence():
    proposals = [_proposal("scoring", "trade_threshold"), _proposal("risk_overlay", "max_theme_pct")]
    kept = apply_evidence_gate(proposals, _EVIDENCE)
    assert len(kept) == 1
    assert kept[0]["mutation"]["field"] == "trade_threshold"
    assert kept[0]["evidence"]  # evidence attached


def test_gate_drops_everything_when_no_evidence_available():
    empty = {"near_miss": {}, "attribution": {}, "calibration_sample_size": 0, "weight_components": []}
    kept = apply_evidence_gate([_proposal("scoring", "trade_threshold")], empty)
    assert kept == []


def test_gather_evidence_handles_missing_reports(tmp_path):
    ev = gather_evidence(tmp_path)
    assert ev["near_miss"] == {}
    assert ev["calibration_sample_size"] == 0


def test_gather_evidence_extracts_overlay_component_ic(tmp_path):
    import json

    out = tmp_path / "runtime" / "analytics"
    out.mkdir(parents=True)
    (out / "calibration_report.json").write_text(json.dumps({
        "sample_size": 20,
        "attribution": {
            "1": [
                {"component": "final_rank_delta", "ic": 0.31},
                {"component": "regime_multiplier", "ic": -0.2},
            ]
        },
    }), encoding="utf-8")

    ev = gather_evidence(tmp_path)

    assert ev["overlay_components"] == [
        {"source": "calibration.overlay_component_ic", "horizon_d": "1", "component": "final_rank_delta", "ic": 0.31},
        {"source": "calibration.overlay_component_ic", "horizon_d": "1", "component": "regime_multiplier", "ic": -0.2},
    ]


def _overlay_evidence_bundle(component: str, ic: float) -> dict:
    return {
        "near_miss": {},
        "attribution": {},
        "calibration_sample_size": 15,
        "weight_components": [],
        "overlay_components": [
            {"source": "calibration.overlay_component_ic", "horizon_d": "5",
             "component": component, "ic": ic},
        ],
    }


def test_overlay_factor_weight_proposal_is_supported_by_factor_alpha_ic():
    from trading_agent.growth.evidence import evidence_for_proposal
    ev = _overlay_evidence_bundle("factor_alpha", 0.15)
    proposal = {"mutation": {"module": "overlay", "field": "factor_weight", "current": 0.0, "proposed": 0.05}}
    items = evidence_for_proposal(proposal, ev)
    assert any(i["component"] == "factor_alpha" for i in items)


def test_overlay_ai_weight_proposal_is_supported_by_ai_composite_ic():
    from trading_agent.growth.evidence import evidence_for_proposal
    ev = _overlay_evidence_bundle("ai_composite", 0.10)
    proposal = {"mutation": {"module": "overlay", "field": "ai_weight", "current": 0.0, "proposed": 0.05}}
    items = evidence_for_proposal(proposal, ev)
    assert any(i["component"] == "ai_composite" for i in items)


def test_overlay_unknown_field_yields_no_evidence():
    from trading_agent.growth.evidence import evidence_for_proposal
    ev = _overlay_evidence_bundle("factor_alpha", 0.20)
    proposal = {"mutation": {"module": "overlay", "field": "unknown_field", "current": 0.0, "proposed": 0.1}}
    items = evidence_for_proposal(proposal, ev)
    assert items == []
