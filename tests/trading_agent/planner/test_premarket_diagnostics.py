from __future__ import annotations

from pathlib import Path

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import read_json, write_json
from trading_agent.planner.premarket_diagnostics import build_premarket_diagnostics, build_premarket_diagnostics_from_paths


def test_premarket_diagnostics_identifies_missing_catalyst_scores() -> None:
    payload = build_premarket_diagnostics(
        run_date="2026-06-15",
        candidate_scores={
            "symbols": {
                "AVGO": {
                    "score": 66.1,
                    "warnings": [],
                    "diagnostics": {
                        "dsa": {"available": True},
                        "technical": {"available": True},
                        "kronos": {"available": True},
                        "quote": {"available": True},
                        "catalyst": {"available": True, "missing_numeric_score": True},
                    },
                }
            }
        },
        risk_overlay={
            "watchlist_score_threshold": 35.0,
            "trade_score_threshold": 50.0,
            "market_regime": "normal",
            "watchlist_candidates": ["AVGO"],
            "tradable_candidates": ["AVGO"],
            "no_trade_reasons": [],
        },
        daily_plan={"plan_state": "trade_ready", "market_regime": "normal", "allowed_actions": ["small_limit_buy"]},
    )

    assert payload["missing_catalyst_score_count"] == 1
    assert payload["top_candidate"] == "AVGO"
    assert payload["threshold_values"]["trade_threshold"] == 50.0


def test_premarket_diagnostics_distinguishes_no_scored_from_no_tradable() -> None:
    observe_only = build_premarket_diagnostics(
        run_date="2026-06-15",
        candidate_scores={
            "symbols": {
                "AVGO": {
                    "score": 46.48,
                    "warnings": ["missing_component:catalyst"],
                    "diagnostics": {
                        "dsa": {"available": True},
                        "technical": {"available": True},
                        "kronos": {"available": True},
                        "quote": {"available": True},
                        "catalyst": {"available": False, "missing_numeric_score": True},
                    },
                }
            }
        },
        risk_overlay={
            "watchlist_score_threshold": 35.0,
            "trade_score_threshold": 50.0,
            "market_regime": "observe_only",
            "watchlist_candidates": ["AVGO"],
            "tradable_candidates": [],
            "no_trade_reasons": ["no_tradable_candidates_above_threshold"],
        },
        daily_plan={"plan_state": "observe_only", "market_regime": "observe_only", "allowed_actions": []},
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
            "no_trade_reasons": ["no_scored_candidates"],
        },
        daily_plan={"plan_state": "no_trade", "market_regime": "no_trade", "allowed_actions": []},
    )

    assert "scored_candidates_exist_but_none_tradable" in observe_only["warnings"]
    assert observe_only["final_daily_plan_state"]["plan_state"] == "observe_only"
    assert no_scores["candidate_count"] == 0
    assert "scored_candidates_exist_but_none_tradable" not in no_scores["warnings"]


def test_premarket_diagnostics_file_is_created(tmp_path: Path) -> None:
    root = tmp_path
    paths = build_runtime_paths(root, run_date="2026-06-15")
    paths.planner_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        paths.candidate_scores_path,
        {
            "symbols": {
                "AVGO": {
                    "score": 66.1,
                    "warnings": ["missing_component:catalyst"],
                    "diagnostics": {
                        "dsa": {"available": True},
                        "technical": {"available": True, "warning": "unmapped_technical_action:promote", "raw_action": "promote"},
                        "kronos": {"available": True},
                        "quote": {"available": True},
                        "catalyst": {"available": True, "missing_numeric_score": True},
                    },
                }
            }
        },
    )
    write_json(
        paths.risk_overlay_path,
        {
            "watchlist_score_threshold": 35.0,
            "trade_score_threshold": 50.0,
            "market_regime": "observe_only",
            "watchlist_candidates": ["AVGO"],
            "tradable_candidates": [],
            "no_trade_reasons": ["no_tradable_candidates_above_threshold"],
        },
    )
    write_json(paths.daily_plan_path, {"plan_state": "observe_only", "market_regime": "observe_only", "allowed_actions": []})

    result = build_premarket_diagnostics_from_paths(root, "2026-06-15")
    saved = read_json(paths.premarket_diagnostics_path)

    assert paths.premarket_diagnostics_path.exists()
    assert result["top_candidate"] == "AVGO"
    assert saved["top_candidate"] == "AVGO"
    assert saved["threshold_values"]["watchlist_threshold"] == 35.0
