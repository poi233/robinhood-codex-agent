from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from trading_agent.policy.candidate_selector import RankedCandidate
from trading_agent.policy.advisory_overlay import overlay_for_symbol
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


COMMON_ETFS = {"SPY", "QQQ", "IWM", "SMH", "VOO", "ARKK", "ARKW", "ARKG", "QTUM"}


def _portfolio_equity(inputs: PolicyInputs) -> float:
    buying_power = float((inputs.account or {}).get("buying_power") or (inputs.capital_snapshot or {}).get("sizing_buying_power") or 0.0)
    positions_value = sum(float(position.quantity * position.market_price) for position in inputs.positions.values())
    return round(buying_power + positions_value, 2)


def _symbol_metadata(inputs: PolicyInputs, symbol: str) -> tuple[str, bool]:
    dynamic = ((inputs.dynamic_allowlist.get("symbol_scores") or {}).get(symbol) or {})
    daily_rule = ((inputs.daily_plan or {}).get("symbol_trade_rules") or {}).get(symbol) or {}
    theme = str(dynamic.get("theme") or daily_rule.get("sector") or "single_name")
    is_etf = symbol in COMMON_ETFS or theme in {"broad_beta", "etf", "index"}
    return theme, is_etf


def _position_notional(inputs: PolicyInputs, symbol: str) -> float:
    position = inputs.positions.get(symbol)
    if not position:
        return 0.0
    return round(float(position.quantity * position.market_price), 2)


def _theme_notional(inputs: PolicyInputs, theme: str) -> float:
    total = 0.0
    for symbol, position in inputs.positions.items():
        current_theme, _ = _symbol_metadata(inputs, symbol)
        if current_theme == theme:
            total += float(position.quantity * position.market_price)
    return round(total, 2)


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
    portfolio_equity = max(portfolio_equity, buying_power)
    theme, is_etf = _symbol_metadata(inputs, candidate.symbol)
    existing_symbol_notional = _position_notional(inputs, candidate.symbol)
    existing_theme_notional = _theme_notional(inputs, theme)
    stock_weight_cap = portfolio_equity * float(profile.get("max_single_stock_weight", 1.0))
    etf_weight_cap = portfolio_equity * float(profile.get("max_etf_weight", 1.0))
    theme_weight_cap = portfolio_equity * float(profile.get("max_theme_weight", 1.0))
    remaining_symbol_weight_cap = max(0.0, stock_weight_cap - existing_symbol_notional)
    remaining_type_cap = max(0.0, (etf_weight_cap if is_etf else stock_weight_cap) - existing_symbol_notional)
    remaining_theme_cap = max(0.0, theme_weight_cap - existing_theme_notional)

    final_notional = min(
        notional_by_risk,
        symbol_cap,
        daily_cap,
        daily_remaining,
        buying_power_after_buffer,
        remaining_symbol_weight_cap,
        remaining_type_cap,
        remaining_theme_cap,
    )
    final_notional *= profile_multiplier
    overlay = overlay_for_symbol(inputs.advisory_overlay, candidate.symbol)
    advisory_multiplier = max(0.0, min(1.0, float(overlay.size_multiplier or 0.0)))
    final_notional *= advisory_multiplier
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
            "advisory_overlay": advisory_multiplier,
        },
        reason_codes=[
            "risk_sizing_ok",
            *(
                ["advisory_overlay_size_multiplier"]
                if advisory_multiplier < 1.0
                else []
            ),
            "cash_buffer_ok",
            "symbol_weight_ok",
            "theme_weight_ok",
            "etf_weight_ok" if is_etf else "stock_weight_ok",
        ],
    )
