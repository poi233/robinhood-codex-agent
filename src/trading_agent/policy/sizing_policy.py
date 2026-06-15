from __future__ import annotations

from dataclasses import dataclass, field

from trading_agent.policy.candidate_selector import RankedCandidate
from trading_agent.policy.models import PolicyInputs
from trading_agent.policy.price_policy import BuyPriceDecision
from trading_agent.policy.risk import buying_power_remaining, daily_notional_remaining


@dataclass(frozen=True)
class SizeDecision:
    quantity: float
    estimated_notional: float
    risk_budget: float
    max_loss_at_stop: float | None
    applied_multipliers: dict[str, float] = field(default_factory=dict)
    reason_codes: list[str] = field(default_factory=list)
    blocked_reason: str | None = None


def _score_multiplier(score: float) -> float:
    if score >= 93:
        return 1.0
    if score >= 88:
        return 0.75
    if score >= 82:
        return 0.5
    return 0.0


def _market_multiplier(inputs: PolicyInputs) -> float:
    regime = str((inputs.risk_overlay or {}).get("market_regime") or (inputs.daily_plan or {}).get("market_regime") or "").lower()
    if regime in {"aggressive_ok", "risk_on", "normal"}:
        return 1.0
    if regime in {"neutral", "premarket"}:
        return 0.5
    return 0.0


def _research_multiplier(candidate: RankedCandidate) -> float:
    if candidate.research_score >= 80:
        return 1.0
    if candidate.research_score >= 60:
        return 0.85
    if candidate.research_score > 0:
        return 0.5
    return 0.0


def decide_size(inputs: PolicyInputs, candidate: RankedCandidate, price: BuyPriceDecision) -> SizeDecision:
    if price.blocked_reason:
        return SizeDecision(0.0, 0.0, 0.0, None, blocked_reason=price.blocked_reason)

    buying_power = float(buying_power_remaining(inputs) or 0.0)
    if buying_power <= 0:
        return SizeDecision(0.0, 0.0, 0.0, None, blocked_reason="missing_buying_power")
    profile = inputs.policy_profile
    portfolio_equity = float((inputs.capital_snapshot or {}).get("sizing_buying_power") or inputs.account.get("buying_power") or 0.0)
    risk_budget = portfolio_equity * float(profile.get("per_trade_risk_pct", 0.005))
    if risk_budget <= 0 or not price.risk_per_share:
        return SizeDecision(0.0, 0.0, risk_budget, None, blocked_reason="risk_budget_exhausted")

    shares_by_risk = risk_budget / price.risk_per_share
    notional_by_risk = shares_by_risk * price.limit_price
    score_multiplier = _score_multiplier(candidate.candidate_score)
    market_multiplier = _market_multiplier(inputs)
    research_multiplier = _research_multiplier(candidate)
    profile_multiplier = score_multiplier * market_multiplier * research_multiplier
    if profile_multiplier <= 0:
        return SizeDecision(0.0, 0.0, risk_budget, None, blocked_reason="profile_multiplier_blocked")

    risk_rules = ((inputs.risk_overlay.get("symbol_trade_rules") or {}).get(candidate.symbol) or {})
    symbol_cap = float(risk_rules.get("max_notional") or inputs.risk_overlay.get("max_single_order_notional") or inputs.risk_caps.get("max_single_order_notional") or 0.0)
    daily_cap = float(inputs.risk_overlay.get("max_daily_notional") or inputs.risk_caps.get("max_daily_notional") or 0.0)
    daily_remaining = daily_notional_remaining(inputs)
    cash_buffer = buying_power * float(profile.get("cash_buffer_pct", 0.1))
    buying_power_after_buffer = max(0.0, buying_power - cash_buffer)

    final_notional = min(notional_by_risk, symbol_cap, daily_cap, daily_remaining, buying_power_after_buffer)
    final_notional *= profile_multiplier
    final_notional = round(final_notional, 2)
    if final_notional < float(profile.get("minimum_trade_notional", 10.0)):
        return SizeDecision(0.0, final_notional, risk_budget, None, blocked_reason="minimum_trade_notional_blocked")

    quantity = round(final_notional / price.limit_price, 8)
    if quantity <= 0:
        return SizeDecision(0.0, final_notional, risk_budget, None, blocked_reason="size_too_small")
    max_loss = round(quantity * price.risk_per_share, 2)
    return SizeDecision(
        quantity=quantity,
        estimated_notional=final_notional,
        risk_budget=round(risk_budget, 2),
        max_loss_at_stop=max_loss,
        applied_multipliers={
            "score": score_multiplier,
            "market": market_multiplier,
            "research": research_multiplier,
        },
        reason_codes=["risk_sizing_ok"],
    )
