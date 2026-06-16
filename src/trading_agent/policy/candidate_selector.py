from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from trading_agent.policy.models import PolicyInputs
from trading_agent.policy.risk import eligible_symbols, has_open_order, losing_position_exists, quote_is_fresh, quote_is_tradeable
from trading_agent.policy.scoring import score_symbol
from trading_agent.policy.technical import technical_symbol_payload


@dataclass(frozen=True)
class RankedCandidate:
    symbol: str
    candidate_score: float
    trade_readiness_score: float
    technical_score: float
    research_score: float
    catalyst_score: float
    liquidity_score: float
    reason_codes: list[str] = field(default_factory=list)


def _candidate_components(inputs: PolicyInputs, symbol: str) -> tuple[float, float, float, float, float]:
    candidate_payload = ((inputs.candidate_scores.get("symbols") or {}).get(symbol) or {})
    components = candidate_payload.get("components") or {}
    candidate_total = float(candidate_payload.get("total_score") or candidate_payload.get("score") or score_symbol(inputs, symbol))
    technical_score = float(components.get("technical") or candidate_total)
    research = inputs.research_reports.get(symbol) or {}
    bias = str(research.get("research_bias") or "").lower()
    research_score = {
        "bullish": 80.0,
        "neutral_bullish": 72.0,
        "neutral": 60.0,
        "cautious": 40.0,
        "avoid": 0.0,
    }.get(bias, 60.0)
    catalyst_payload = ((inputs.catalyst_snapshot.get("symbols") or {}).get(symbol) or {})
    catalyst_score = float(catalyst_payload.get("score") or components.get("catalyst") or 60.0)
    quote = inputs.quotes.get(symbol)
    liquidity_score = 80.0 if quote and quote.is_fresh and quote.price > 0 else 0.0
    return candidate_total, technical_score, research_score, catalyst_score, liquidity_score


def hard_block_reasons(inputs: PolicyInputs, symbol: str) -> list[str]:
    reasons: list[str] = []
    if inputs.kill_switch_present:
        reasons.append("kill_switch_present")
    if not inputs.daily_plan:
        reasons.append("missing_daily_plan")
    if not inputs.data_status_summary or inputs.data_status_summary.get("execution_blocking"):
        reasons.append("data_status_blocked")
    risk_rules = ((inputs.risk_overlay.get("symbol_trade_rules") or {}).get(symbol) or {})
    if inputs.risk_overlay and not risk_rules.get("allow_buy", True):
        reasons.append("risk_overlay_blocks_buy")
    research = inputs.research_reports.get(symbol) or {}
    if research.get("invalid_conditions_triggered") is True:
        reasons.append("research_invalid_condition")
    if symbol not in inputs.quotes:
        reasons.append("missing_quote")
    elif not quote_is_fresh(inputs, symbol):
        reasons.append("stale_quote")
    elif not quote_is_tradeable(inputs, symbol):
        reasons.append("missing_quote")
    if has_open_order(inputs, symbol):
        reasons.append("open_order_exists")
    if losing_position_exists(inputs, symbol):
        reasons.append("average_down_blocked")
    if not technical_symbol_payload(inputs, symbol):
        reasons.append("missing_technical_levels")
    reasons.extend(_cooldown_reasons(inputs, symbol))
    return reasons


def _days_since(run_date: str, prior_date: str) -> int | None:
    try:
        current = date.fromisoformat(run_date)
        prior = date.fromisoformat(prior_date)
    except ValueError:
        return None
    return (current - prior).days


def _cooldown_reasons(inputs: PolicyInputs, symbol: str) -> list[str]:
    profile = inputs.policy_profile or {}
    usage = inputs.daily_usage if isinstance(inputs.daily_usage, dict) else {}
    reasons: list[str] = []
    if not bool(profile.get("allow_average_down", False)) and losing_position_exists(inputs, symbol):
        reasons.append("average_down_blocked")
    last_buy_date = str((usage.get("last_buy_date_by_symbol") or {}).get(symbol) or "")
    if last_buy_date:
        elapsed = _days_since(inputs.run_date, last_buy_date)
        cooldown = int(profile.get("cooldown_days_after_buy", 0) or 0)
        if elapsed is not None and elapsed < cooldown:
            reasons.append("cooldown_after_buy")
    last_stop_date = str((usage.get("last_stop_date_by_symbol") or {}).get(symbol) or "")
    if last_stop_date:
        elapsed = _days_since(inputs.run_date, last_stop_date)
        cooldown = int(profile.get("cooldown_days_after_stop", 0) or 0)
        if elapsed is not None and elapsed < cooldown:
            reasons.append("cooldown_after_stop")
    if int(usage.get("new_positions_today", 0) or 0) >= int(profile.get("max_new_positions_per_day", 99) or 99):
        reasons.append("daily_new_position_limit_reached")
    if int(usage.get("new_positions_this_week", 0) or 0) >= int(profile.get("max_new_positions_per_week", 999) or 999):
        reasons.append("weekly_new_position_limit_reached")
    return reasons


def rank_candidates(inputs: PolicyInputs) -> tuple[list[RankedCandidate], dict[str, list[str]]]:
    ranked: list[RankedCandidate] = []
    blocked: dict[str, list[str]] = {}
    for symbol in eligible_symbols(inputs):
        reasons = hard_block_reasons(inputs, symbol)
        if reasons:
            blocked[symbol] = reasons
            continue
        candidate_total, technical_score, research_score, catalyst_score, liquidity_score = _candidate_components(inputs, symbol)
        trade_readiness_score = (
            0.35 * candidate_total
            + 0.25 * technical_score
            + 0.10 * liquidity_score
            + 0.10 * research_score
            + 0.05 * catalyst_score
        )
        ranked.append(
            RankedCandidate(
                symbol=symbol,
                candidate_score=round(candidate_total, 2),
                trade_readiness_score=round(trade_readiness_score, 2),
                technical_score=round(technical_score, 2),
                research_score=round(research_score, 2),
                catalyst_score=round(catalyst_score, 2),
                liquidity_score=round(liquidity_score, 2),
                reason_codes=["candidate_ranked", "hard_blocks_cleared"],
            )
        )
    ranked.sort(key=lambda item: (-item.trade_readiness_score, -item.candidate_score, item.symbol))
    return ranked, blocked
