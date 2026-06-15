from __future__ import annotations

from trading_agent.planner.risk_overlay import build_risk_overlay, resolve_buying_power


def test_paper_mode_uses_paper_ledger_buying_power_not_robinhood_snapshot() -> None:
    result = resolve_buying_power(
        trading_mode="paper",
        paper_account={"cash": 400000.0, "equity": 400000.0},
        account_snapshot={"buying_power": 100.0},
        paper_starting_cash=400000.0,
    )

    assert result["buying_power"] == 400000.0
    assert result["source"] == "paper_account"
    assert result["paper_buying_power"] == 400000.0
    assert result["real_account_buying_power"] == 100.0


def test_paper_mode_falls_back_to_starting_cash_when_ledger_is_missing() -> None:
    result = resolve_buying_power(
        trading_mode="paper",
        paper_account=None,
        account_snapshot={"buying_power": 100.0},
        paper_starting_cash=400000.0,
    )

    assert result["buying_power"] == 400000.0
    assert result["source"] == "paper_starting_cash"
    assert result["paper_buying_power"] == 400000.0
    assert result["real_account_buying_power"] == 100.0


def test_live_mode_uses_robinhood_account_snapshot_buying_power() -> None:
    result = resolve_buying_power(
        trading_mode="live",
        paper_account={"cash": 400000.0},
        account_snapshot={"buying_power": 100.0},
        paper_starting_cash=400000.0,
    )

    assert result["buying_power"] == 100.0
    assert result["source"] == "robinhood_account_snapshot"
    assert result["paper_buying_power"] == 400000.0
    assert result["real_account_buying_power"] == 100.0


def test_risk_overlay_blocks_execution_when_market_is_closed() -> None:
    overlay = build_risk_overlay(
        run_date="2026-06-14",
        trading_mode="paper",
        risk_tier=3,
        risk_caps={"max_single_order_notional": 5000, "max_daily_notional": 20000},
        market_calendar={"data_status": "ok", "is_trading_day": False, "session": "closed"},
        capital_snapshot={"sizing_buying_power": 400000.0, "sizing_source": "paper_starting_cash"},
        account_snapshot={"agentic_account_identified": True, "data_status": "ok"},
        candidate_scores={"symbols": {"SMH": {"score": 82, "blocked": False}}},
        data_status_summary={"execution_blocking": True, "reason_codes": ["dsa:market_closed"]},
    )

    assert overlay["market_regime"] == "no_trade"
    assert overlay["allowed_actions"] == []
    assert overlay["max_single_order_notional"] == 0
    assert overlay["max_daily_notional"] == 0
    assert "market_closed" in overlay["no_trade_reasons"]


def test_risk_overlay_uses_capital_snapshot_for_paper_sizing() -> None:
    overlay = build_risk_overlay(
        run_date="2026-06-15",
        trading_mode="paper",
        risk_tier=3,
        risk_caps={"max_single_order_notional": 5000, "max_daily_notional": 20000},
        market_calendar={"data_status": "ok", "is_trading_day": True, "session": "premarket"},
        capital_snapshot={"sizing_buying_power": 400000.0, "sizing_source": "paper_starting_cash"},
        account_snapshot={"agentic_account_identified": True, "data_status": "ok", "buying_power": 100.0},
        candidate_scores={"symbols": {"SMH": {"score": 82, "blocked": False, "score_status": "scored"}}},
        data_status_summary={"execution_blocking": False, "reason_codes": []},
    )

    assert overlay["market_regime"] == "aggressive_ok"
    assert overlay["allowed_actions"] == ["small_limit_buy", "partial_take_profit"]
    assert overlay["max_single_order_notional"] == 5000
    assert overlay["max_daily_notional"] == 20000
    assert overlay["capital_snapshot"]["sizing_buying_power"] == 400000.0
    assert overlay["today_watchlist"] == ["SMH"]
    assert overlay["watchlist_candidates"] == ["SMH"]
    assert overlay["tradable_candidates"] == ["SMH"]
    assert overlay["symbol_trade_rules"]["SMH"]["allow_buy"] is True


def test_risk_overlay_does_not_block_premarket_when_trading_day_is_true_even_if_session_is_closed() -> None:
    overlay = build_risk_overlay(
        run_date="2026-06-15",
        trading_mode="paper",
        risk_tier=3,
        risk_caps={"max_single_order_notional": 5000, "max_daily_notional": 20000},
        market_calendar={"data_status": "ok", "is_trading_day": True, "session": "closed"},
        capital_snapshot={"sizing_buying_power": 400000.0, "sizing_source": "paper_starting_cash"},
        account_snapshot={"agentic_account_identified": True, "data_status": "ok", "buying_power": 100.0},
        candidate_scores={"symbols": {"SMH": {"score": 82, "blocked": False, "score_status": "scored"}}},
        data_status_summary={"execution_blocking": False, "reason_codes": []},
    )

    assert overlay["market_regime"] == "aggressive_ok"
    assert "market_closed" not in overlay["no_trade_reasons"]


def test_risk_overlay_distinguishes_no_tradable_candidates_from_no_scored_candidates() -> None:
    overlay = build_risk_overlay(
        run_date="2026-06-15",
        trading_mode="paper",
        risk_tier=3,
        risk_caps={"max_single_order_notional": 5000, "max_daily_notional": 20000},
        market_calendar={"data_status": "ok", "is_trading_day": True, "session": "premarket"},
        capital_snapshot={"sizing_buying_power": 400000.0, "sizing_source": "paper_starting_cash"},
        account_snapshot={"agentic_account_identified": True, "data_status": "ok", "buying_power": 100.0},
        candidate_scores={
            "symbols": {
                "AVGO": {"score": 46.48, "blocked": False, "score_status": "scored"},
                "NVDA": {"score": 41.12, "blocked": False, "score_status": "scored"},
            }
        },
        data_status_summary={"execution_blocking": False, "reason_codes": []},
    )

    assert overlay["market_regime"] == "observe_only"
    assert overlay["watchlist_candidates"] == ["AVGO", "NVDA"]
    assert overlay["tradable_candidates"] == []
    assert overlay["today_watchlist"] == ["AVGO", "NVDA"]
    assert overlay["allowed_actions"] == []
    assert overlay["no_trade_reasons"] == ["no_tradable_candidates_above_threshold"]
    assert overlay["symbol_trade_rules"]["AVGO"]["allow_buy"] is False


def test_risk_overlay_keeps_candidates_above_trade_threshold_as_tradable() -> None:
    overlay = build_risk_overlay(
        run_date="2026-06-15",
        trading_mode="paper",
        risk_tier=3,
        risk_caps={"max_single_order_notional": 5000, "max_daily_notional": 20000},
        market_calendar={"data_status": "ok", "is_trading_day": True, "session": "premarket"},
        capital_snapshot={"sizing_buying_power": 400000.0, "sizing_source": "paper_starting_cash"},
        account_snapshot={"agentic_account_identified": True, "data_status": "ok", "buying_power": 100.0},
        candidate_scores={
            "symbols": {
                "AVGO": {"score": 66.1, "blocked": False, "score_status": "scored"},
                "NVDA": {"score": 41.12, "blocked": False, "score_status": "scored"},
            }
        },
        data_status_summary={"execution_blocking": False, "reason_codes": []},
    )

    assert overlay["watchlist_candidates"] == ["AVGO", "NVDA"]
    assert overlay["tradable_candidates"] == ["AVGO"]
    assert overlay["today_watchlist"] == ["AVGO", "NVDA"]
    assert overlay["allowed_actions"] == ["small_limit_buy", "partial_take_profit"]


def test_risk_overlay_true_empty_candidate_list_still_reports_no_scored_candidates() -> None:
    overlay = build_risk_overlay(
        run_date="2026-06-15",
        trading_mode="paper",
        risk_tier=3,
        risk_caps={"max_single_order_notional": 5000, "max_daily_notional": 20000},
        market_calendar={"data_status": "ok", "is_trading_day": True, "session": "premarket"},
        capital_snapshot={"sizing_buying_power": 400000.0, "sizing_source": "paper_starting_cash"},
        account_snapshot={"agentic_account_identified": True, "data_status": "ok", "buying_power": 100.0},
        candidate_scores={"symbols": {}},
        data_status_summary={"execution_blocking": False, "reason_codes": []},
    )

    assert overlay["watchlist_candidates"] == []
    assert overlay["tradable_candidates"] == []
    assert overlay["no_trade_reasons"] == ["no_scored_candidates"]


def test_risk_overlay_uses_configured_scoring_thresholds() -> None:
    overlay = build_risk_overlay(
        run_date="2026-06-15",
        trading_mode="paper",
        risk_tier=3,
        risk_caps={"max_single_order_notional": 5000, "max_daily_notional": 20000},
        market_calendar={"data_status": "ok", "is_trading_day": True, "session": "premarket"},
        capital_snapshot={"sizing_buying_power": 400000.0, "sizing_source": "paper_starting_cash"},
        account_snapshot={"agentic_account_identified": True, "data_status": "ok", "buying_power": 100.0},
        candidate_scores={"symbols": {"AVGO": {"score": 66.1, "blocked": False, "score_status": "scored"}}},
        data_status_summary={"execution_blocking": False, "reason_codes": []},
        scoring_profile={
            "name": "balanced",
            "watchlist_threshold": 40.0,
            "trade_threshold": 60.0,
            "high_conviction_threshold": 82.0,
            "min_effective_coverage": 0.55,
        },
    )

    assert overlay["scoring_profile"] == "balanced"
    assert overlay["watchlist_score_threshold"] == 40.0
    assert overlay["trade_score_threshold"] == 60.0
    assert overlay["high_conviction_threshold"] == 82.0
    assert overlay["min_effective_coverage"] == 0.55
    assert overlay["tradable_candidates"] == ["AVGO"]
