import json
from datetime import datetime
from pathlib import Path

from trading_agent.core.context import build_experiment_paths, build_runtime_paths
from trading_agent.core.time import PT
from trading_agent.growth.shadow_runner import (
    _challenger_policy_profile,
    build_challenger_inputs,
    build_challenger_risk_overlay,
    run_shadow_experiment,
)
from trading_agent.policy.models import PolicyInputs, Quote


def _experiment(proposed_trade_threshold: float) -> dict:
    return {
        "experiment_id": "exp_2026-06-14_scoring_trade_threshold",
        "challenger_strategy_id": "baseline_v1__trade_threshold_40",
        "status": "active_shadow",
        "module": "scoring",
        "field": "trade_threshold",
        "current": 50.0,
        "proposed": proposed_trade_threshold,
    }


def _seed_champion_artifacts(agent_root: Path, run_date: str, *, score: float) -> None:
    paths = build_runtime_paths(agent_root, run_date=run_date)
    paths.candidate_scores_path.parent.mkdir(parents=True, exist_ok=True)
    paths.candidate_scores_path.write_text(json.dumps({
        "date": run_date,
        "symbols": {"NVDA": {"score": score, "total_score": score, "score_status": "scored",
                              "components": {"technical": score}}},
    }), encoding="utf-8")
    (agent_root / "src" / "config").mkdir(parents=True, exist_ok=True)
    (agent_root / "src" / "config" / "risk_tiers.json").write_text(
        json.dumps({"0": {"max_single_order_notional": 10, "max_daily_notional": 25}}), encoding="utf-8")
    paths.capital_snapshot_path.write_text(json.dumps({"sizing_buying_power": 25.0}), encoding="utf-8")
    paths.account_snapshot_path.write_text(json.dumps({"agentic_account_identified": True, "data_status": "ok"}), encoding="utf-8")
    paths.market_calendar_path.write_text(json.dumps({"is_trading_day": True}), encoding="utf-8")
    paths.data_status_summary_path.write_text(json.dumps({"execution_blocking": False, "reason_codes": []}), encoding="utf-8")


def test_build_experiment_paths_are_isolated():
    exp_paths = build_experiment_paths(Path("/agent"), run_date="2026-06-14", strategy_id="chal_x")
    assert exp_paths.shadow_decisions_log_path == Path(
        "/agent/runtime/state/runs/2026-06-14/experiments/chal_x/shadow_decisions.jsonl"
    )
    champion = build_runtime_paths(Path("/agent"), run_date="2026-06-14").decisions_log_path
    assert champion != exp_paths.shadow_decisions_log_path
    assert "experiments/chal_x" in str(exp_paths.shadow_orders_log_path)


def test_lower_trade_threshold_makes_more_candidates_tradable(tmp_path):
    # Score 45 is below champion threshold 50 (not tradable) but above challenger 40 (tradable).
    _seed_champion_artifacts(tmp_path, "2026-06-14", score=45.0)
    champion_overlay = build_challenger_risk_overlay(
        tmp_path, "2026-06-14", _experiment(50.0), trading_mode="paper", risk_tier=0)
    challenger_overlay = build_challenger_risk_overlay(
        tmp_path, "2026-06-14", _experiment(40.0), trading_mode="paper", risk_tier=0)
    assert "NVDA" not in champion_overlay["tradable_candidates"]
    assert "NVDA" in challenger_overlay["tradable_candidates"]


def _minimal_inputs(run_date: str) -> PolicyInputs:
    fresh = datetime.now(tz=PT).isoformat()
    return PolicyInputs(
        run_date=run_date,
        trading_mode="paper",
        risk_tier=0,
        today_allowlist=["NVDA"],
        daily_plan={"date": run_date, "market_regime": "normal", "allowed_actions": ["small_limit_buy"],
                    "today_watchlist": ["NVDA"], "symbol_trade_rules": {}},
        candidate_scores={"date": run_date, "symbols": {"NVDA": {"score": 45.0, "total_score": 45.0,
                          "score_status": "scored", "components": {"technical": 45.0}}}},
        account={"buying_power": 25.0},
        quotes={"NVDA": Quote(symbol="NVDA", price=100.0, previous_close=101.0, timestamp=fresh)},
    )


def test_challenger_policy_profile_loads_named_profile():
    # A policy-setup challenger names its own profile; it must resolve to that profile's setups.
    profile = _challenger_policy_profile(Path("."), {"policy_profile": "range_reversion"})
    assert profile is not None
    assert profile["setups"] == ["range_reversion"]
    # A pure scoring/threshold challenger (no policy_profile) keeps the champion's profile.
    assert _challenger_policy_profile(Path("."), {"module": "scoring", "field": "trade_threshold"}) is None


def test_build_challenger_inputs_swaps_policy_profile_when_provided():
    champion = _minimal_inputs("2026-06-14")
    champion.policy_profile = {"name": "champion", "setups": ["pullback", "breakout"]}
    challenger_profile = {"name": "range_reversion", "setups": ["range_reversion"]}

    swapped = build_challenger_inputs(champion, {"symbol_trade_rules": {}}, policy_profile=challenger_profile)
    assert swapped.policy_profile["setups"] == ["range_reversion"]
    # Champion inputs are not mutated, and omitting the profile keeps the champion's.
    assert champion.policy_profile["setups"] == ["pullback", "breakout"]
    kept = build_challenger_inputs(champion, {"symbol_trade_rules": {}})
    assert kept.policy_profile["setups"] == ["pullback", "breakout"]


def test_run_shadow_experiment_writes_isolated_ledger_only(tmp_path):
    _seed_champion_artifacts(tmp_path, "2026-06-14", score=45.0)
    champion_inputs = _minimal_inputs("2026-06-14")

    decision = run_shadow_experiment(
        tmp_path, run_date="2026-06-14", experiment=_experiment(40.0),
        champion_inputs=champion_inputs, trading_mode="paper", risk_tier=0)

    exp_paths = build_experiment_paths(tmp_path, run_date="2026-06-14", strategy_id="baseline_v1__trade_threshold_40")
    assert exp_paths.shadow_decisions_log_path.exists()
    rows = [json.loads(line) for line in exp_paths.shadow_decisions_log_path.read_text(encoding="utf-8").splitlines()]
    assert rows and rows[0]["experiment_id"] == "exp_2026-06-14_scoring_trade_threshold"
    assert decision["decision"] in {"would_trade", "no_action", "blocked"}
    # Champion's real decision log is never written by the shadow runner.
    champion_decisions = build_runtime_paths(tmp_path, run_date="2026-06-14").decisions_log_path
    assert not champion_decisions.exists()

    # G9: the challenger gets its own isolated paper ledger (seeded on first run).
    from trading_agent.core.context import build_experiment_runtime_paths
    exp_runtime = build_experiment_runtime_paths(tmp_path, run_date="2026-06-14", strategy_id="baseline_v1__trade_threshold_40")
    assert exp_runtime.paper_account_path.exists()
    assert "experiments/baseline_v1__trade_threshold_40/paper" in str(exp_runtime.paper_account_path)
    # Champion paper ledger is never created by the shadow runner.
    assert not build_runtime_paths(tmp_path, run_date="2026-06-14").paper_account_path.exists()
