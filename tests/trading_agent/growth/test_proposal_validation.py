import json
from pathlib import Path

from trading_agent.growth.policy import load_growth_policy
from trading_agent.growth.validator import validate_proposal
from trading_agent.growth.proposal_review import validate_proposal_file

POLICY = load_growth_policy(Path.cwd())


def _proposal(mutation: dict) -> dict:
    return {
        "proposal_id": "2026-06-16_scoring_trade_threshold",
        "based_on_observation": "high_no_trade_rate",
        "mutation": mutation,
        "rationale": "test",
        "status": "proposed",
    }


def test_valid_proposal_marked_validated():
    result = validate_proposal(
        _proposal({"module": "scoring", "field": "trade_threshold", "current": 50, "proposed": 56}),
        POLICY,
    )
    assert result["status"] == "validated"
    assert result["ok"] is True
    assert result["violations"] == []
    assert result["proposal_id"] == "2026-06-16_scoring_trade_threshold"


def test_forbidden_proposal_marked_rejected():
    result = validate_proposal(
        _proposal({"module": "risk", "field": "per_trade_risk_pct", "current": 0.005, "proposed": 0.02}),
        POLICY,
    )
    assert result["status"] == "rejected"
    assert result["ok"] is False
    assert any("forbidden_mutation" in v for v in result["violations"])


def test_proposal_without_mutation_is_rejected():
    result = validate_proposal({"proposal_id": "x", "status": "proposed"}, POLICY)
    assert result["status"] == "rejected"
    assert result["ok"] is False


def test_non_paper_only_policy_rejects_otherwise_valid_proposal():
    result = validate_proposal(
        _proposal({"module": "scoring", "field": "trade_threshold", "current": 50, "proposed": 56}),
        {**POLICY, "mode": "live"},
    )
    assert result["status"] == "rejected"
    assert any("paper_only" in v for v in result["violations"])


def test_validate_proposal_file_writes_sibling_validation_json(tmp_path):
    config_dir = tmp_path / "src" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "growth_policy.json").write_text(
        (Path.cwd() / "src" / "config" / "growth_policy.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    proposal_path = tmp_path / "runtime" / "strategy_proposals" / "2026-06-16" / "proposal_001_scoring_trade_threshold.json"
    proposal_path.parent.mkdir(parents=True)
    proposal_path.write_text(
        json.dumps(_proposal({"module": "scoring", "field": "trade_threshold", "current": 50, "proposed": 56})),
        encoding="utf-8",
    )

    out = validate_proposal_file(tmp_path, proposal_path)

    assert out == proposal_path.with_name("proposal_001_scoring_trade_threshold_validation.json")
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "validated"
    # The original proposal file is never mutated.
    original = json.loads(proposal_path.read_text(encoding="utf-8"))
    assert original["status"] == "proposed"
