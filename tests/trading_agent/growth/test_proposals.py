import json
from pathlib import Path

from trading_agent.growth.policy import load_growth_policy
from trading_agent.growth.proposals import (
    _OVERLAY_DEFAULTS,
    build_proposals,
    default_proposals_dir,
    evidence_proposals,
    proposals_from_observations,
    write_proposals,
)

POLICY = load_growth_policy(Path.cwd())
CURRENT = {("scoring", "trade_threshold"): 50.0, ("scoring", "watchlist_threshold"): 35.0}
CURRENT_WITH_OVERLAY = {**CURRENT, **_OVERLAY_DEFAULTS}


def test_rarely_trades_observation_proposes_lower_trade_threshold():
    observations = [{"type": "high_no_trade_rate", "module": "global"}]
    proposals = proposals_from_observations(observations, POLICY, CURRENT, run_date="2026-06-16")
    assert len(proposals) == 1
    mutation = proposals[0]["mutation"]
    assert mutation["field"] == "trade_threshold"
    assert mutation["proposed"] < mutation["current"]  # lower threshold => trade more
    assert proposals[0]["validation"]["ok"] is True
    assert proposals[0]["status"] == "proposed"


def test_theme_concentration_observation_proposes_tighter_watchlist():
    observations = [{"type": "recurring_theme_concentration", "module": "scoring"}]
    proposals = proposals_from_observations(observations, POLICY, CURRENT, run_date="2026-06-16")
    assert len(proposals) == 1
    assert proposals[0]["mutation"]["field"] == "watchlist_threshold"
    assert proposals[0]["mutation"]["proposed"] > proposals[0]["mutation"]["current"]


def test_every_proposal_only_touches_whitelisted_validated_fields():
    observations = [
        {"type": "high_no_trade_rate", "module": "global"},
        {"type": "recurring_theme_concentration", "module": "scoring"},
    ]
    proposals = proposals_from_observations(observations, POLICY, CURRENT, run_date="2026-06-16")
    for proposal in proposals:
        assert proposal["validation"]["ok"] is True
        assert proposal["validation"]["violations"] == []


def test_no_observations_yields_no_proposals():
    assert proposals_from_observations([], POLICY, CURRENT, run_date="2026-06-16") == []


def test_no_op_at_bound_is_not_proposed():
    # trade_threshold already at its min: lowering further is a clamped no-op, drop it.
    current = {("scoring", "trade_threshold"): 30.0}  # min is 30 in growth_policy
    observations = [{"type": "high_no_trade_rate", "module": "global"}]
    assert proposals_from_observations(observations, POLICY, current, run_date="2026-06-16") == []


def test_frequency_cap_limits_number_of_proposals():
    capped_policy = {**POLICY, "proposal": {**POLICY.get("proposal", {}), "max_new_proposals_per_week": 1}}
    observations = [
        {"type": "high_no_trade_rate", "module": "global"},
        {"type": "recurring_theme_concentration", "module": "scoring"},
    ]
    proposals = proposals_from_observations(observations, capped_policy, CURRENT, run_date="2026-06-16")
    assert len(proposals) == 1


def test_write_proposals_emits_json_and_md_and_changes_nothing(tmp_path):
    # The agent root needs the real safety policy, exactly like production.
    config_dir = tmp_path / "src" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "growth_policy.json").write_text(
        (Path.cwd() / "src" / "config" / "growth_policy.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    # Seed a run that triggers high_no_trade_rate: 5 no-trade decisions, no fills.
    dec_dir = tmp_path / "runtime" / "logs" / "runs" / "2026-06-15" / "audit"
    dec_dir.mkdir(parents=True)
    with (dec_dir / "decisions.jsonl").open("w", encoding="utf-8") as fh:
        for i in range(5):
            fh.write(json.dumps({
                "timestamp": f"2026-06-15T07:0{i}:00-0700",
                "decision": "no_trade",
                "blocked_reasons": ["below_trade_threshold"],
            }) + "\n")
    (tmp_path / "runtime" / "state" / "runs" / "2026-06-15").mkdir(parents=True, exist_ok=True)

    paths = write_proposals(tmp_path, run_date="2026-06-16")

    assert paths, "expected at least one proposal written"
    proposals_dir = default_proposals_dir(tmp_path, "2026-06-16")
    json_files = sorted(proposals_dir.glob("*.json"))
    md_files = sorted(proposals_dir.glob("*.md"))
    assert json_files and md_files
    payload = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert payload["mutation"]["module"] == "scoring"
    assert payload["status"] == "proposed"
    # Champion config is never touched.
    assert not (tmp_path / "src" / "config" / "scoring_profiles.yaml").exists()


def test_build_proposals_reads_real_repo_policy_and_config():
    # Smoke: against the real repo, with no seeded observations there is nothing to propose,
    # and it must not raise.
    proposals = build_proposals(Path.cwd(), since="2099-01-01", until="2099-01-02")
    assert proposals == []


# --- M5: Evidence-based overlay proposal rules ---

def _overlay_evidence(factor_ic: float | None = None, ai_ic: float | None = None) -> dict:
    components = []
    if factor_ic is not None:
        components.append({"source": "calibration.overlay_component_ic", "horizon_d": "5",
                           "component": "factor_alpha", "ic": factor_ic})
    if ai_ic is not None:
        components.append({"source": "calibration.overlay_component_ic", "horizon_d": "5",
                           "component": "ai_composite", "ic": ai_ic})
    return {"near_miss": {}, "attribution": {}, "calibration_sample_size": 20,
            "weight_components": [], "overlay_components": components}


def test_overlay_factor_positive_ic_proposes_bump():
    ev = _overlay_evidence(factor_ic=0.18)
    proposals = evidence_proposals(ev, POLICY, CURRENT_WITH_OVERLAY, run_date="2026-06-18")
    assert len(proposals) == 1
    p = proposals[0]
    assert p["mutation"]["module"] == "overlay"
    assert p["mutation"]["field"] == "factor_weight"
    assert p["mutation"]["proposed"] > p["mutation"]["current"]
    assert p["validation"]["ok"] is True


def test_overlay_ai_positive_ic_proposes_bump():
    ev = _overlay_evidence(ai_ic=0.12)
    proposals = evidence_proposals(ev, POLICY, CURRENT_WITH_OVERLAY, run_date="2026-06-18")
    assert len(proposals) == 1
    assert proposals[0]["mutation"]["field"] == "ai_weight"
    assert proposals[0]["mutation"]["proposed"] > 0


def test_overlay_negative_ic_yields_no_proposal():
    ev = _overlay_evidence(factor_ic=-0.05, ai_ic=-0.10)
    proposals = evidence_proposals(ev, POLICY, CURRENT_WITH_OVERLAY, run_date="2026-06-18")
    assert proposals == []


def test_overlay_both_positive_ic_yields_two_proposals():
    ev = _overlay_evidence(factor_ic=0.15, ai_ic=0.08)
    proposals = evidence_proposals(ev, POLICY, CURRENT_WITH_OVERLAY, run_date="2026-06-18")
    fields = {p["mutation"]["field"] for p in proposals}
    assert fields == {"factor_weight", "ai_weight"}
    for p in proposals:
        assert p["validation"]["ok"] is True


def test_overlay_no_evidence_yields_no_proposal():
    ev = _overlay_evidence()
    proposals = evidence_proposals(ev, POLICY, CURRENT_WITH_OVERLAY, run_date="2026-06-18")
    assert proposals == []


def test_overlay_proposal_at_max_is_not_proposed():
    # factor_weight already at its max (0.25): bumping further is a clamped no-op.
    current_at_max = {**CURRENT_WITH_OVERLAY, ("overlay", "factor_weight"): 0.25}
    ev = _overlay_evidence(factor_ic=0.20)
    proposals = evidence_proposals(ev, POLICY, current_at_max, run_date="2026-06-18")
    assert all(p["mutation"]["field"] != "factor_weight" for p in proposals)
