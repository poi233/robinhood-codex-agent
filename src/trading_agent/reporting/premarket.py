from __future__ import annotations

from datetime import datetime
from typing import Any

from trading_agent.reporting.trader_watch_levels import build_trader_watch_levels


def build_fail_closed_daily_plan(run_date: str, reason: str) -> dict[str, object]:
    return {
        "date": run_date,
        "plan_status": "failed_closed",
        "plan_state": "no_trade",
        "market_regime": "no_trade",
        "allowed_actions": [],
        "today_watchlist": [],
        "no_trade_reasons": [reason],
        "notes": reason,
    }


def determine_plan_state(risk_overlay: dict[str, Any]) -> str:
    market_regime = str((risk_overlay or {}).get("market_regime") or "").lower()
    tradable_candidates = list((risk_overlay or {}).get("tradable_candidates") or [])
    watchlist_candidates = list((risk_overlay or {}).get("watchlist_candidates") or [])
    if market_regime in {"no_trade", "risk_off"}:
        return "no_trade"
    if tradable_candidates:
        return "trade_ready"
    if watchlist_candidates:
        return "observe_only"
    return "no_trade"


def normalize_daily_plan_state(run_date: str, daily_plan: dict[str, Any], risk_overlay: dict[str, Any]) -> dict[str, Any]:
    payload = dict(daily_plan or {})
    overlay = dict(risk_overlay or {})
    plan_state = determine_plan_state(overlay)
    payload["date"] = run_date
    payload["plan_state"] = plan_state
    if overlay:
        payload["today_watchlist"] = list(overlay.get("today_watchlist") or payload.get("today_watchlist") or [])
        payload["allowed_actions"] = list(overlay.get("allowed_actions") or [])
        payload["symbol_trade_rules"] = dict(overlay.get("symbol_trade_rules") or payload.get("symbol_trade_rules") or {})
        payload["no_trade_reasons"] = list(dict.fromkeys(list(overlay.get("no_trade_reasons") or payload.get("no_trade_reasons") or [])))
        payload["watchlist_candidates"] = list(overlay.get("watchlist_candidates") or [])
        payload["tradable_candidates"] = list(overlay.get("tradable_candidates") or [])
    if plan_state == "trade_ready":
        payload["market_regime"] = str(overlay.get("market_regime") or payload.get("market_regime") or "normal")
    elif plan_state == "observe_only":
        payload["market_regime"] = "observe_only"
    else:
        payload["market_regime"] = "no_trade"
    return payload


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
