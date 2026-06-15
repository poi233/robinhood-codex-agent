from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import read_json, write_json
from trading_agent.core.time import PT
from trading_agent.planner.scoring_profiles import DEFAULT_SCORING_PROFILE, load_scoring_profile


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


def _candidate_score(payload: dict[str, Any]) -> float:
    return float(payload.get("score", 0) or 0)


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
    scoring_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scoring_profile = dict(scoring_profile or DEFAULT_SCORING_PROFILE)
    watchlist_threshold = float(scoring_profile.get("watchlist_threshold", DEFAULT_SCORING_PROFILE["watchlist_threshold"]))
    trade_threshold = float(scoring_profile.get("trade_threshold", DEFAULT_SCORING_PROFILE["trade_threshold"]))
    high_conviction_threshold = float(scoring_profile.get("high_conviction_threshold", DEFAULT_SCORING_PROFILE["high_conviction_threshold"]))
    no_trade_reasons: list[str] = []
    hard_block_reasons: list[str] = []
    if not _is_trading_day(market_calendar):
        hard_block_reasons.append("market_closed")
    if account_snapshot.get("agentic_account_identified") is not True or account_snapshot.get("data_status") == "failed":
        hard_block_reasons.append("account_snapshot_unavailable")
    if data_status_summary.get("execution_blocking"):
        hard_block_reasons.extend(str(reason) for reason in data_status_summary.get("reason_codes", []))

    symbols_payload = candidate_scores.get("symbols") or {}
    scored_candidates = [
        symbol
        for symbol, payload in sorted(
            symbols_payload.items(),
            key=lambda item: (-_candidate_score(item[1] or {}), item[0]),
        )
        if isinstance(payload, dict) and not payload.get("blocked") and payload.get("score_status") != "blocked"
    ][:8]
    watchlist_candidates = [symbol for symbol in scored_candidates if _candidate_score(symbols_payload[symbol]) >= watchlist_threshold][:8]
    tradable_candidates = [
        symbol
        for symbol in watchlist_candidates
        if _candidate_score(symbols_payload[symbol]) >= trade_threshold
        and (symbols_payload[symbol] or {}).get("score_status") == "scored"
    ][:8]

    if not scored_candidates:
        no_trade_reasons.append("no_scored_candidates")
    elif not tradable_candidates:
        no_trade_reasons.append("no_tradable_candidates_above_threshold")
    no_trade_reasons = hard_block_reasons + no_trade_reasons

    max_single = float(risk_caps.get("max_single_order_notional", 0) or 0)
    max_daily = float(risk_caps.get("max_daily_notional", 0) or 0)
    sizing_buying_power = float(capital_snapshot.get("sizing_buying_power", 0) or 0)
    max_single = min(max_single, sizing_buying_power)
    max_daily = min(max_daily, sizing_buying_power)

    if hard_block_reasons:
        allowed_actions: list[str] = []
        max_single = 0.0
        max_daily = 0.0
        market_regime = "no_trade"
        risk_level = "no_trade"
        risk_multiplier = 0.0
        today_watchlist = watchlist_candidates
    elif tradable_candidates:
        allowed_actions = ["small_limit_buy", "partial_take_profit"]
        market_regime = "aggressive_ok" if any(_candidate_score(symbols_payload.get(symbol) or {}) >= high_conviction_threshold for symbol in tradable_candidates) else "normal"
        risk_level = "aggressive" if market_regime == "aggressive_ok" else "normal"
        risk_multiplier = 1.0
        today_watchlist = watchlist_candidates
    else:
        allowed_actions = []
        market_regime = "observe_only"
        risk_level = "observe_only"
        risk_multiplier = 0.0
        today_watchlist = watchlist_candidates

    return {
        "date": run_date,
        "generated_at": datetime.now(tz=PT).isoformat(),
        "trading_mode": trading_mode,
        "risk_tier": risk_tier,
        "scoring_profile": scoring_profile.get("name", DEFAULT_SCORING_PROFILE["name"]),
        "watchlist_score_threshold": watchlist_threshold,
        "trade_score_threshold": trade_threshold,
        "high_conviction_threshold": high_conviction_threshold,
        "min_effective_coverage": float(scoring_profile.get("min_effective_coverage", DEFAULT_SCORING_PROFILE["min_effective_coverage"])),
        "market_regime": market_regime,
        "risk_level": risk_level,
        "risk_multiplier": risk_multiplier,
        "watchlist_candidates": watchlist_candidates,
        "tradable_candidates": tradable_candidates,
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
                "allow_buy": symbol in tradable_candidates and bool(allowed_actions),
                "breakout_allowed": symbol in tradable_candidates and bool(allowed_actions),
                "pullback_buy_allowed": symbol in tradable_candidates and bool(allowed_actions),
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
    scoring_profile = load_scoring_profile(paths.config_dir)
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
        scoring_profile=scoring_profile,
    )
    write_json(paths.risk_overlay_path, payload)
    return payload
