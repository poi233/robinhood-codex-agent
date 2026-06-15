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
from trading_agent.policy.technical import as_float, entry_zone, price_in_zone, technical_symbol_payload


@dataclass(frozen=True)
class BuyEvaluation:
    intent: OrderIntent | None
    blocked_reasons: list[str] = field(default_factory=list)


def _buy_technical_plan(inputs: PolicyInputs, symbol: str, base_notional: float) -> tuple[float, float, list[str]] | None:
    technical = technical_symbol_payload(inputs, symbol)
    if not technical:
        return None

    quote = inputs.quotes[symbol]
    long_setup = technical.get("long_setup") or {}
    status = str(long_setup.get("status") or "").lower()
    if status not in {"active", "watch"}:
        return None

    no_trade_zone = technical.get("no_trade_zone") or {}
    no_trade_low = as_float(no_trade_zone.get("low"))
    no_trade_high = as_float(no_trade_zone.get("high"))
    if price_in_zone(quote.price, no_trade_low, no_trade_high):
        return None

    trigger_above = as_float(long_setup.get("trigger_above"))
    entry_low, entry_high = entry_zone(technical, "long_setup")
    in_entry_zone = price_in_zone(quote.price, entry_low, entry_high)
    breakout_ready = trigger_above is not None and quote.price >= trigger_above
    if not in_entry_zone and not breakout_ready:
        return None

    do_not_chase_above = as_float(long_setup.get("do_not_chase_above"))
    if do_not_chase_above is not None and quote.price > do_not_chase_above:
        return None

    symbol_rules = ((inputs.daily_plan or {}).get("symbol_trade_rules") or {}).get(symbol) or {}
    breakout_allowed = bool(symbol_rules.get("breakout_allowed", False))
    if breakout_ready and not in_entry_zone and not breakout_allowed:
        return None

    invalidation_below = as_float(long_setup.get("invalidation_below"))
    if invalidation_below is None or invalidation_below >= quote.price:
        return None

    risk_ratio = (quote.price - invalidation_below) / quote.price
    if risk_ratio <= 0 or risk_ratio > 0.08:
        return None

    technical_scale = min(1.0, 0.01 / risk_ratio)
    zone_width = None
    if entry_low is not None and entry_high is not None and quote.price > 0:
        zone_width = max(0.0, (entry_high - entry_low) / quote.price)
    if zone_width and zone_width > 0.02:
        technical_scale *= min(1.0, 0.02 / zone_width)

    adjusted_notional = round(base_notional * technical_scale, 2)
    if adjusted_notional <= 0:
        return None

    reason_codes = ["technical_levels_ok", "risk_cap_ok"]
    if in_entry_zone:
        reason_codes.append("entry_zone_match")
    if breakout_ready:
        reason_codes.append("breakout_triggered")
    if technical_scale < 0.999:
        reason_codes.append("technical_size_reduced")
    return quote.price, adjusted_notional, reason_codes


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
        technical_plan = _buy_technical_plan(inputs, symbol, notional)
        if technical_plan is None:
            first_blocked = first_blocked or ["technical_entry_not_ready"]
            continue
        limit_price, notional, reason_codes = technical_plan
        quantity = round(notional / limit_price, 8)
        if quantity <= 0:
            first_blocked = first_blocked or ["technical_size_too_small"]
            continue
        return BuyEvaluation(
            OrderIntent(
                symbol=symbol,
                side="buy",
                order_type="limit",
                limit_price=limit_price,
                estimated_notional=notional,
                quantity=quantity,
                reason_codes=["score_pass", "market_regime_ok", *reason_codes],
                confidence=score / 100,
            )
        )
    return BuyEvaluation(None, first_blocked or ["no_buy_candidate"])
