from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import read_json, write_json
from trading_agent.core.time import PT


def _as_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _paper_buying_power(paper_account: dict[str, Any] | None, paper_starting_cash: float) -> tuple[float, str]:
    if isinstance(paper_account, dict):
        cash = _as_float(paper_account.get("cash"))
        if cash is not None:
            return cash, "paper_account"
        buying_power = _as_float(paper_account.get("buying_power"))
        if buying_power is not None:
            return buying_power, "paper_account"
    return round(float(paper_starting_cash), 2), "paper_starting_cash"


def resolve_buying_power(
    *,
    trading_mode: str,
    paper_account: dict[str, Any] | None,
    account_snapshot: dict[str, Any] | None,
    paper_starting_cash: float,
) -> dict[str, Any]:
    mode = (trading_mode or "paper").lower()
    real_account_buying_power = _as_float((account_snapshot or {}).get("buying_power"))
    paper_buying_power, paper_source = _paper_buying_power(paper_account, paper_starting_cash)

    if mode == "paper":
        return {
            "trading_mode": mode,
            "buying_power": paper_buying_power,
            "source": paper_source,
            "paper_buying_power": paper_buying_power,
            "real_account_buying_power": real_account_buying_power,
        }

    return {
        "trading_mode": mode,
        "buying_power": real_account_buying_power,
        "source": "robinhood_account_snapshot" if real_account_buying_power is not None else "missing_robinhood_account_snapshot",
        "paper_buying_power": paper_buying_power,
        "real_account_buying_power": real_account_buying_power,
    }


def build_capital_snapshot(
    *,
    run_date: str,
    trading_mode: str,
    paper_account: dict[str, Any] | None,
    account_snapshot: dict[str, Any] | None,
    paper_starting_cash: float,
) -> dict[str, Any]:
    resolved = resolve_buying_power(
        trading_mode=trading_mode,
        paper_account=paper_account,
        account_snapshot=account_snapshot,
        paper_starting_cash=paper_starting_cash,
    )
    return {
        "date": run_date,
        "generated_at": datetime.now(tz=PT).isoformat(),
        "trading_mode": resolved["trading_mode"],
        "sizing_buying_power": resolved["buying_power"],
        "sizing_source": resolved["source"],
        "paper_buying_power": resolved["paper_buying_power"],
        "real_account_buying_power": resolved["real_account_buying_power"],
        "notes": (
            "Paper mode uses local paper ledger cash for sizing; Robinhood buying power remains "
            "a read-only real-account reference."
            if resolved["trading_mode"] == "paper"
            else "Review/live modes use Robinhood account snapshot buying power for sizing."
        ),
    }


def _calendar_trading_day_flag(market_calendar: dict[str, Any]) -> bool | None:
    if market_calendar.get("is_trading_day") is True or market_calendar.get("trading_day") is True:
        return True
    if market_calendar.get("is_trading_day") is False or market_calendar.get("trading_day") is False:
        return False
    return None


def _is_trading_day(market_calendar: dict[str, Any]) -> bool:
    return _calendar_trading_day_flag(market_calendar) is True


def build_risk_overlay(
    *,
    run_date: str,
    trading_mode: str,
    risk_tier: int,
    risk_caps: dict[str, Any],
    market_calendar: dict[str, Any],
    capital_snapshot: dict[str, Any],
    account_snapshot: dict[str, Any],
    candidate_scores: dict[str, Any],
    data_status_summary: dict[str, Any],
) -> dict[str, Any]:
    no_trade_reasons: list[str] = []
    if not _is_trading_day(market_calendar):
        no_trade_reasons.append("market_closed")
    if account_snapshot.get("agentic_account_identified") is not True or account_snapshot.get("data_status") == "failed":
        no_trade_reasons.append("account_snapshot_unavailable")
    if data_status_summary.get("execution_blocking"):
        no_trade_reasons.extend(str(reason) for reason in data_status_summary.get("reason_codes", []))

    symbols_payload = candidate_scores.get("symbols") or {}
    ranked = [
        symbol
        for symbol, payload in sorted(
            symbols_payload.items(),
            key=lambda item: (-float((item[1] or {}).get("score", 0) or 0), item[0]),
        )
        if isinstance(payload, dict) and not payload.get("blocked") and float(payload.get("score", 0) or 0) >= 50
    ][:8]
    if not ranked:
        no_trade_reasons.append("no_scored_candidates")

    max_single = float(risk_caps.get("max_single_order_notional", 0) or 0)
    max_daily = float(risk_caps.get("max_daily_notional", 0) or 0)
    sizing_buying_power = float(capital_snapshot.get("sizing_buying_power", 0) or 0)
    max_single = min(max_single, sizing_buying_power)
    max_daily = min(max_daily, sizing_buying_power)

    if no_trade_reasons:
        allowed_actions: list[str] = []
        max_single = 0.0
        max_daily = 0.0
        market_regime = "no_trade"
        risk_level = "no_trade"
        risk_multiplier = 0.0
        today_watchlist: list[str] = []
    else:
        allowed_actions = ["small_limit_buy", "partial_take_profit"]
        market_regime = "aggressive_ok" if any(float((symbols_payload.get(symbol) or {}).get("score", 0) or 0) >= 80 for symbol in ranked) else "normal"
        risk_level = "aggressive" if market_regime == "aggressive_ok" else "normal"
        risk_multiplier = 1.0
        today_watchlist = ranked

    return {
        "date": run_date,
        "generated_at": datetime.now(tz=PT).isoformat(),
        "trading_mode": trading_mode,
        "risk_tier": risk_tier,
        "market_regime": market_regime,
        "risk_level": risk_level,
        "risk_multiplier": risk_multiplier,
        "allowed_actions": allowed_actions,
        "today_watchlist": today_watchlist,
        "blocked_symbols": [symbol for symbol, payload in symbols_payload.items() if isinstance(payload, dict) and payload.get("blocked")],
        "max_single_order_notional": round(max_single, 2),
        "max_daily_notional": round(max_daily, 2),
        "capital_snapshot": capital_snapshot,
        "no_trade_reasons": list(dict.fromkeys(no_trade_reasons)),
        "symbol_trade_rules": {
            symbol: {
                "score": symbols_payload[symbol]["score"],
                "max_notional": round(max_single, 2),
                "breakout_allowed": True,
                "pullback_buy_allowed": True,
                "setup": "use precomputed technical/catalyst artifacts; final planner writes narrative",
            }
            for symbol in today_watchlist
        },
    }


def _read_json_or_empty(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = read_json(path)
    return payload if isinstance(payload, dict) else {}


def build_risk_overlay_from_paths(agent_root: Path, run_date: str, *, trading_mode: str, risk_tier: int) -> dict[str, Any]:
    paths = build_runtime_paths(agent_root, run_date=run_date)
    risk_config = _read_json_or_empty(paths.config_dir / "risk_tiers.json")
    risk_caps = risk_config.get(str(risk_tier)) or {}
    payload = build_risk_overlay(
        run_date=run_date,
        trading_mode=trading_mode,
        risk_tier=risk_tier,
        risk_caps=risk_caps,
        market_calendar=_read_json_or_empty(paths.market_calendar_path),
        capital_snapshot=_read_json_or_empty(paths.capital_snapshot_path),
        account_snapshot=_read_json_or_empty(paths.account_snapshot_path),
        candidate_scores=_read_json_or_empty(paths.candidate_scores_path),
        data_status_summary=_read_json_or_empty(paths.data_status_summary_path),
    )
    write_json(paths.risk_overlay_path, payload)
    return payload
