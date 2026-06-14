from __future__ import annotations

from datetime import datetime

from trading_agent.reporting.trader_watch_levels import build_trader_watch_levels


def build_fail_closed_daily_plan(run_date: str, reason: str) -> dict[str, object]:
    return {
        "date": run_date,
        "plan_status": "failed_closed",
        "market_regime": "no_trade",
        "allowed_actions": [],
        "today_watchlist": [],
        "no_trade_reasons": [reason],
        "notes": reason,
    }


def build_premarket_archive_payload(
    run_date: str,
    daily_plan: dict[str, object],
    technical_payload: dict[str, object],
) -> dict[str, object]:
    return {
        "date": run_date,
        "generated_at": datetime.now().astimezone().isoformat(),
        "summary": "premarket archive",
        "daily_plan": daily_plan,
        "trader_watch_levels": build_trader_watch_levels(technical_payload),
    }
