from __future__ import annotations

from dataclasses import dataclass, field

from trading_agent.policy.models import OrderIntent, PolicyInputs
from trading_agent.policy.risk import (
    buying_power_remaining,
    daily_notional_remaining,
    eligible_symbols,
    has_open_order,
    losing_position_exists,
    quote_is_tradeable,
    single_order_cap,
)
from trading_agent.policy.scoring import score_symbol


@dataclass(frozen=True)
class BuyEvaluation:
    intent: OrderIntent | None
    blocked_reasons: list[str] = field(default_factory=list)


def evaluate_buy(inputs: PolicyInputs) -> BuyEvaluation:
    if not inputs.daily_plan:
        return BuyEvaluation(None, ["missing_daily_plan"])
    if inputs.daily_plan.get("market_regime") in {"risk_off", "no_trade"}:
        return BuyEvaluation(None, ["market_regime_blocks_buy"])
    if "small_limit_buy" not in inputs.daily_plan.get("allowed_actions", []):
        return BuyEvaluation(None, ["buy_not_allowed"])

    symbols = eligible_symbols(inputs)
    if not symbols:
        return BuyEvaluation(None, ["allowlist_intersection_empty"])

    first_blocked: list[str] = []
    for symbol in symbols:
        score = score_symbol(inputs, symbol)
        if score < 80:
            first_blocked = first_blocked or ["score_below_threshold"]
            continue
        if not quote_is_tradeable(inputs, symbol):
            first_blocked = first_blocked or ["missing_quote"]
            continue
        if has_open_order(inputs, symbol):
            first_blocked = first_blocked or ["open_order_exists"]
            continue
        if losing_position_exists(inputs, symbol):
            first_blocked = first_blocked or ["average_down_blocked"]
            continue

        remaining = daily_notional_remaining(inputs)
        if remaining <= 0:
            first_blocked = first_blocked or ["daily_notional_exhausted"]
            continue
        buying_power = buying_power_remaining(inputs)
        notional = min(single_order_cap(inputs, symbol), remaining)
        if buying_power is not None:
            notional = min(notional, buying_power)
        if notional <= 0:
            first_blocked = first_blocked or ["single_order_notional_exhausted"]
            continue

        quote = inputs.quotes[symbol]
        return BuyEvaluation(
            OrderIntent(
                symbol=symbol,
                side="buy",
                order_type="limit",
                limit_price=quote.price,
                estimated_notional=notional,
                quantity=round(notional / quote.price, 8),
                reason_codes=["score_pass", "market_regime_ok", "risk_cap_ok"],
                confidence=score / 100,
            )
        )
    return BuyEvaluation(None, first_blocked or ["no_buy_candidate"])
