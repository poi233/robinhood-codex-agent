from __future__ import annotations

from trading_agent.planner.risk_overlay import build_risk_overlay
from trading_agent.planner.scoring import score_candidate
from trading_agent.reporting.premarket import normalize_daily_plan_state


def test_regression_20260615_avgo_candidate_clears_trade_threshold_after_normalization() -> None:
    avgo = score_candidate(
        symbol="AVGO",
        dsa={"selected_candidates": [{"symbol": "AVGO", "score": 70}]},
        kronos={"symbols": {"AVGO": {"signal": "neutral", "confidence": 0.5}}},
        technical={"symbols": {"AVGO": {"technical_action": "promote"}}},
        quote={"symbols": {"AVGO": {"score": 64.77}}},
        catalyst={"symbols": {"AVGO": {"status": "completed"}}},
    )
    amd = score_candidate(
        symbol="AMD",
        dsa={"selected_candidates": [{"symbol": "AMD", "score": 70}]},
        kronos={"symbols": {"AMD": {"signal": "bearish", "confidence": 0.95}}},
        technical={"symbols": {"AMD": {"technical_action": "reduce"}}},
        quote={"symbols": {"AMD": {"score": 52.0}}},
        catalyst={"symbols": {"AMD": {"status": "partial"}}},
    )

    overlay = build_risk_overlay(
        run_date="2026-06-15",
        trading_mode="paper",
        risk_tier=3,
        risk_caps={"max_single_order_notional": 5000, "max_daily_notional": 20000},
        market_calendar={"data_status": "ok", "is_trading_day": True, "session": "premarket"},
        capital_snapshot={"sizing_buying_power": 400000.0, "sizing_source": "paper_starting_cash"},
        account_snapshot={"agentic_account_identified": True, "data_status": "ok", "buying_power": 100.0},
        candidate_scores={"symbols": {"AVGO": avgo, "AMD": amd}},
        data_status_summary={"execution_blocking": False, "reason_codes": []},
    )
    daily_plan = normalize_daily_plan_state("2026-06-15", {"market_regime": "no_trade"}, overlay)

    assert avgo["components"]["technical"] == 82
    assert avgo["components"]["catalyst"] == 50
    assert avgo["score"] > 50
    assert "no_scored_candidates" not in overlay["no_trade_reasons"]
    assert overlay["tradable_candidates"] == ["AVGO"]
    assert daily_plan["plan_state"] == "trade_ready"


def test_regression_20260615_preserves_watchlist_when_scores_exist_but_none_tradable() -> None:
    avgo = score_candidate(
        symbol="AVGO",
        dsa={"selected_candidates": [{"symbol": "AVGO", "score": 46.48}]},
        kronos={"symbols": {"AVGO": {"signal": "neutral", "confidence": 0.5}}},
        technical={"symbols": {"AVGO": {"technical_action": "observe"}}},
        quote={"symbols": {"AVGO": {"score": 46.48}}},
        catalyst={"symbols": {"AVGO": {"status": "completed"}}},
    )

    overlay = build_risk_overlay(
        run_date="2026-06-15",
        trading_mode="paper",
        risk_tier=3,
        risk_caps={"max_single_order_notional": 5000, "max_daily_notional": 20000},
        market_calendar={"data_status": "ok", "is_trading_day": True, "session": "premarket"},
        capital_snapshot={"sizing_buying_power": 400000.0, "sizing_source": "paper_starting_cash"},
        account_snapshot={"agentic_account_identified": True, "data_status": "ok", "buying_power": 100.0},
        candidate_scores={"symbols": {"AVGO": avgo}},
        data_status_summary={"execution_blocking": False, "reason_codes": []},
    )
    daily_plan = normalize_daily_plan_state("2026-06-15", {"market_regime": "no_trade"}, overlay)

    assert overlay["watchlist_candidates"] == ["AVGO"]
    assert overlay["tradable_candidates"] == []
    assert overlay["no_trade_reasons"] == ["no_tradable_candidates_above_threshold"]
    assert daily_plan["plan_state"] == "observe_only"
    assert daily_plan["today_watchlist"] == ["AVGO"]
