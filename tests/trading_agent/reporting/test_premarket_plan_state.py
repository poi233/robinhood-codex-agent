from __future__ import annotations

from trading_agent.reporting.premarket import determine_plan_state, normalize_daily_plan_state


def test_determine_plan_state_returns_no_trade_for_global_blocker() -> None:
    overlay = {
        "market_regime": "no_trade",
        "watchlist_candidates": ["AVGO"],
        "tradable_candidates": [],
        "no_trade_reasons": ["market_closed"],
    }

    assert determine_plan_state(overlay) == "no_trade"


def test_determine_plan_state_returns_observe_only_when_candidates_exist_but_not_tradable() -> None:
    overlay = {
        "market_regime": "observe_only",
        "watchlist_candidates": ["AVGO", "NVDA"],
        "tradable_candidates": [],
        "today_watchlist": ["AVGO", "NVDA"],
        "allowed_actions": [],
        "symbol_trade_rules": {"AVGO": {"allow_buy": False}, "NVDA": {"allow_buy": False}},
        "no_trade_reasons": ["no_tradable_candidates_above_threshold"],
    }

    normalized = normalize_daily_plan_state("2026-06-15", {"market_regime": "no_trade"}, overlay)

    assert determine_plan_state(overlay) == "observe_only"
    assert normalized["plan_state"] == "observe_only"
    assert normalized["market_regime"] == "observe_only"
    assert normalized["today_watchlist"] == ["AVGO", "NVDA"]
    assert normalized["allowed_actions"] == []


def test_determine_plan_state_returns_trade_ready_when_tradable_candidates_exist() -> None:
    overlay = {
        "market_regime": "normal",
        "watchlist_candidates": ["AVGO", "NVDA"],
        "tradable_candidates": ["AVGO"],
        "today_watchlist": ["AVGO", "NVDA"],
        "allowed_actions": ["small_limit_buy", "partial_take_profit"],
        "symbol_trade_rules": {"AVGO": {"allow_buy": True}, "NVDA": {"allow_buy": False}},
        "no_trade_reasons": [],
    }

    normalized = normalize_daily_plan_state("2026-06-15", {"market_regime": "no_trade"}, overlay)

    assert determine_plan_state(overlay) == "trade_ready"
    assert normalized["plan_state"] == "trade_ready"
    assert normalized["market_regime"] == "normal"
    assert normalized["tradable_candidates"] == ["AVGO"]
    assert normalized["allowed_actions"] == ["small_limit_buy", "partial_take_profit"]
