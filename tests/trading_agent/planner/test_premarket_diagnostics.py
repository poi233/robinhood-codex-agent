from __future__ import annotations

from pathlib import Path

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import read_json, write_json
from trading_agent.planner.premarket_diagnostics import build_premarket_diagnostics, build_premarket_diagnostics_from_paths


def _candidate_payload(score: float, *, score_status: str = "scored", missing_catalyst: bool = False, warning: str | None = None) -> dict:
    technical = {"available": True, "score": 82.0}
    if warning:
        technical.update({"warning": warning, "raw_action": warning.split(":")[-1]})
    return {
        "score": score,
        "score_status": score_status,
        "warnings": ["missing_component:catalyst"] if missing_catalyst else [],
        "diagnostics": {
            "dsa": {"available": True},
            "technical": technical,
            "kronos": {"available": True},
            "quote": {"available": True},
            "catalyst": {"available": not missing_catalyst, "missing_numeric_score": missing_catalyst},
        },
    }


def test_premarket_diagnostics_identifies_missing_catalyst_scores_and_thresholds() -> None:
    payload = build_premarket_diagnostics(
        run_date="2026-06-15",
        candidate_scores={"symbols": {"AVGO": _candidate_payload(66.1, missing_catalyst=True)}},
        risk_overlay={
            "watchlist_score_threshold": 35.0,
            "trade_score_threshold": 50.0,
            "market_regime": "normal",
            "watchlist_candidates": ["AVGO"],
            "tradable_candidates": ["AVGO"],
            "today_watchlist": ["AVGO"],
            "allowed_actions": ["small_limit_buy"],
            "risk_level": "normal",
            "no_trade_reasons": [],
        },
        daily_plan={"plan_state": "trade_ready", "market_regime": "normal", "allowed_actions": ["small_limit_buy"]},
        data_status_summary={"execution_blocking": False, "reason_codes": []},
        catalyst_snapshot={"symbols": {"AVGO": {"status": "completed"}}},
        technical_signals={"symbols": {"AVGO": {"technical_action": "promote"}}},
        scoring_profile={
            "name": "balanced",
            "watchlist_threshold": 40.0,
            "trade_threshold": 60.0,
            "high_conviction_threshold": 82.0,
            "min_effective_coverage": 0.55,
        },
    )

    assert payload["missing_catalyst_score_count"] == 1
    assert payload["top_candidate"] == "AVGO"
    assert payload["thresholds"]["trade_threshold"] == 50.0
    assert payload["thresholds"]["scoring_profile"] == "balanced"
    assert payload["thresholds"]["high_conviction_threshold"] == 82.0
    assert payload["thresholds"]["min_effective_coverage"] == 0.55
    assert payload["score_status_counts"]["scored"] == 1
    assert payload["component_coverage"]["technical"] == 1


def test_premarket_diagnostics_distinguishes_no_scored_candidates_from_no_tradable_candidates() -> None:
    observe_only = build_premarket_diagnostics(
        run_date="2026-06-15",
        candidate_scores={"symbols": {"AVGO": _candidate_payload(46.48, missing_catalyst=True)}},
        risk_overlay={
            "watchlist_score_threshold": 35.0,
            "trade_score_threshold": 50.0,
            "market_regime": "observe_only",
            "watchlist_candidates": ["AVGO"],
            "tradable_candidates": [],
            "today_watchlist": ["AVGO"],
            "allowed_actions": [],
            "risk_level": "observe_only",
            "no_trade_reasons": ["no_tradable_candidates_above_threshold"],
        },
        daily_plan={"plan_state": "observe_only", "market_regime": "observe_only", "allowed_actions": [], "today_watchlist": ["AVGO"]},
        data_status_summary={"execution_blocking": False, "reason_codes": []},
        catalyst_snapshot={"symbols": {"AVGO": {"status": "partial"}}},
        technical_signals={"symbols": {"AVGO": {"technical_action": "observe"}}},
    )
    no_scores = build_premarket_diagnostics(
        run_date="2026-06-15",
        candidate_scores={"symbols": {}},
        risk_overlay={
            "watchlist_score_threshold": 35.0,
            "trade_score_threshold": 50.0,
            "market_regime": "no_trade",
            "watchlist_candidates": [],
            "tradable_candidates": [],
            "today_watchlist": [],
            "allowed_actions": [],
            "risk_level": "no_trade",
            "no_trade_reasons": ["no_scored_candidates"],
        },
        daily_plan={"plan_state": "no_trade", "market_regime": "no_trade", "allowed_actions": []},
        data_status_summary={"execution_blocking": True, "reason_codes": ["provider_failed"]},
        catalyst_snapshot={},
        technical_signals={},
    )

    assert "scored_candidates_exist_but_none_tradable" in observe_only["warnings"]
    assert observe_only["final_daily_plan_state"]["plan_state"] == "observe_only"
    assert "scored_candidates_exist_but_none_tradable" not in no_scores["warnings"]
    assert no_scores["scored_candidate_count"] == 0


def test_premarket_diagnostics_warns_when_watchlist_exists_but_daily_plan_is_no_trade() -> None:
    payload = build_premarket_diagnostics(
        run_date="2026-06-15",
        candidate_scores={"symbols": {"AVGO": _candidate_payload(46.48, score_status="insufficient_data", missing_catalyst=True)}},
        risk_overlay={
            "watchlist_score_threshold": 35.0,
            "trade_score_threshold": 50.0,
            "market_regime": "observe_only",
            "watchlist_candidates": ["AVGO"],
            "tradable_candidates": [],
            "today_watchlist": ["AVGO"],
            "allowed_actions": [],
            "risk_level": "observe_only",
            "no_trade_reasons": ["no_tradable_candidates_above_threshold"],
        },
        daily_plan={"plan_state": "no_trade", "market_regime": "no_trade", "allowed_actions": [], "today_watchlist": []},
        data_status_summary={"execution_blocking": False, "reason_codes": []},
        catalyst_snapshot={"symbols": {"AVGO": {"status": "completed"}}},
        technical_signals={"symbols": {"AVGO": {"technical_action": "promote"}}},
    )

    assert "watchlist_candidates_exist_but_daily_plan_no_trade" in payload["warnings"]


def test_premarket_diagnostics_file_is_created_with_final_daily_plan_state(tmp_path: Path) -> None:
    root = tmp_path
    paths = build_runtime_paths(root, run_date="2026-06-15")
    paths.planner_dir.mkdir(parents=True, exist_ok=True)
    paths.signals_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        paths.candidate_scores_path,
        {"symbols": {"AVGO": _candidate_payload(66.1, missing_catalyst=True, warning="unmapped_technical_action:promote")}},
    )
    write_json(
        paths.risk_overlay_path,
        {
            "watchlist_score_threshold": 35.0,
            "trade_score_threshold": 50.0,
            "market_regime": "observe_only",
            "watchlist_candidates": ["AVGO"],
            "tradable_candidates": [],
            "today_watchlist": ["AVGO"],
            "allowed_actions": [],
            "risk_level": "observe_only",
            "no_trade_reasons": ["no_tradable_candidates_above_threshold"],
        },
    )
    write_json(paths.daily_plan_path, {"plan_state": "observe_only", "market_regime": "observe_only", "allowed_actions": [], "today_watchlist": ["AVGO"]})
    write_json(paths.data_status_summary_path, {"execution_blocking": False, "reason_codes": []})
    write_json(paths.catalyst_snapshot_path, {"symbols": {"AVGO": {"status": "completed"}}})
    write_json(paths.technical_signals_path, {"symbols": {"AVGO": {"technical_action": "promote"}}})

    result = build_premarket_diagnostics_from_paths(root, "2026-06-15")
    saved = read_json(paths.premarket_diagnostics_path)

    assert paths.premarket_diagnostics_path.exists()
    assert result["top_candidate"] == "AVGO"
    assert saved["top_candidate"] == "AVGO"
    assert saved["thresholds"]["watchlist_threshold"] == 35.0
    assert saved["final_daily_plan_state"]["plan_state"] == "observe_only"
