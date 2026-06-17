from __future__ import annotations

import os

from trading_agent.policy.models import OrderIntent, PolicyInputs
from trading_agent.policy.risk import has_open_order
from trading_agent.policy.technical import as_float, technical_symbol_payload


def _hard_stop_loss_pct() -> float:
    """Catastrophic hard-stop threshold as a positive fraction (0.08 = sell at −8%). `0` disables it.
    Conservative default: a last-line safety net that only fires on a large adverse move, well below
    normal noise. Paper-only; tune via HARD_STOP_LOSS_PCT in runtime.env(.local)."""
    try:
        return max(0.0, float(os.environ.get("HARD_STOP_LOSS_PCT", "0.08")))
    except (TypeError, ValueError):
        return 0.08


def _evaluate_hard_stop(inputs: PolicyInputs) -> OrderIntent | None:
    """J1 safety net: a full exit whenever a position's loss vs its average cost (measured on the live
    quote) breaches the hard-stop threshold — INDEPENDENT of allowed_actions and of whether technical
    invalidation levels exist. This guarantees every position has an automatic stop even when levels
    are missing (the gap the technical-only `full_invalidation_exit` left). Paper-only: review/live
    are still gated by execution_not_wired."""
    pct = _hard_stop_loss_pct()
    if pct <= 0:
        return None
    for symbol, position in inputs.positions.items():
        symbol = symbol.upper()
        if position.quantity <= 0 or position.average_cost <= 0:
            continue
        if has_open_order(inputs, symbol):
            continue
        quote = inputs.quotes.get(symbol)
        if not quote or not quote.is_fresh or quote.price <= 0:
            continue
        loss = (quote.price - position.average_cost) / position.average_cost
        if loss <= -pct:
            limit_price = round(quote.price * 0.997, 4)
            return OrderIntent(
                symbol=symbol,
                side="sell",
                order_type="limit",
                reference_price=quote.price,
                bid=quote.bid,
                ask=quote.ask,
                spread_bps=quote.spread_bps,
                setup_type="hard_stop",
                limit_price=limit_price,
                estimated_notional=round(position.quantity * limit_price, 2),
                quantity=position.quantity,
                reason_codes=["catastrophic_stop"],
                confidence=0.9,
            )
    return None


def evaluate_sell(inputs: PolicyInputs) -> OrderIntent | None:
    if not inputs.daily_plan:
        return None
    # The hard stop runs before the allowed_actions gate so it fires even on a plan that permits no
    # discretionary sell action — it is the last-line catastrophic stop, not a strategy action.
    hard_stop = _evaluate_hard_stop(inputs)
    if hard_stop is not None:
        return hard_stop
    allowed_actions = set(inputs.daily_plan.get("allowed_actions", []))
    if not ({"partial_take_profit", "risk_exit"} & allowed_actions):
        return None

    for symbol, position in inputs.positions.items():
        symbol = symbol.upper()
        if position.quantity <= 0:
            continue
        if has_open_order(inputs, symbol):
            continue
        quote = inputs.quotes.get(symbol)
        if not quote or not quote.is_fresh or quote.price <= 0:
            continue

        watch = ((inputs.trader_watch_levels.get("symbols") or {}).get(symbol) or {})
        technical = technical_symbol_payload(inputs, symbol)
        if not technical and not watch:
            continue

        reason_codes: list[str] = []
        long_setup = technical.get("long_setup") or {}
        short_setup = technical.get("short_setup") or {}
        partial_target_1 = as_float(watch.get("target_1")) or as_float(long_setup.get("target_1"))
        partial_target_2 = as_float(watch.get("target_2")) or as_float(long_setup.get("target_2"))
        if (
            "partial_take_profit" in allowed_actions
            and position.unrealized_return >= 0.025
            and (
                (partial_target_2 is not None and quote.price >= partial_target_2)
                or (partial_target_1 is not None and quote.price >= partial_target_1)
            )
        ):
            reason_codes.append("partial_take_profit")

        trigger_below = as_float(watch.get("risk_reduction_trigger_below")) or as_float(short_setup.get("trigger_below"))
        risk_target_1 = as_float(watch.get("risk_reduction_target_1")) or as_float(short_setup.get("target_1"))
        risk_target_2 = as_float(watch.get("risk_reduction_target_2")) or as_float(short_setup.get("target_2"))
        invalidation_below = as_float(watch.get("invalidation_below")) or as_float(long_setup.get("invalidation_below"))
        if (
            "risk_exit" in allowed_actions
            and short_setup.get("status") in {"active", "watch"}
            and trigger_below is not None
            and quote.price < trigger_below
        ):
            reason_codes.append("risk_exit")

        if invalidation_below is not None and quote.price <= invalidation_below:
            reason_codes.append("full_invalidation_exit")

        if not reason_codes:
            continue

        sell_fraction = 0.0
        if "partial_take_profit" in reason_codes:
            if partial_target_2 is not None and quote.price >= partial_target_2:
                sell_fraction = max(sell_fraction, 0.5)
            elif partial_target_1 is not None and quote.price >= partial_target_1:
                sell_fraction = max(sell_fraction, 0.25)
        if "risk_exit" in reason_codes:
            if risk_target_2 is not None and quote.price <= risk_target_2:
                sell_fraction = max(sell_fraction, 1.0)
            elif risk_target_1 is not None and quote.price <= risk_target_1:
                sell_fraction = max(sell_fraction, 0.75)
            else:
                sell_fraction = max(sell_fraction, 0.5)
        if "full_invalidation_exit" in reason_codes:
            sell_fraction = 1.0

        quantity = round(max(0.0, min(position.quantity, position.quantity * sell_fraction)), 8)
        if quantity <= 0:
            continue
        limit_price = round(quote.price * 0.997, 4) if "risk_exit" in reason_codes or "full_invalidation_exit" in reason_codes else quote.price
        return OrderIntent(
            symbol=symbol,
            side="sell",
            order_type="limit",
            reference_price=quote.price,
            bid=quote.bid,
            ask=quote.ask,
            spread_bps=quote.spread_bps,
            setup_type="risk_exit" if "risk_exit" in reason_codes or "full_invalidation_exit" in reason_codes else "take_profit",
            limit_price=limit_price,
            estimated_notional=round(quantity * limit_price, 2),
            quantity=quantity,
            stop_price=invalidation_below,
            target_1=partial_target_1,
            target_2=partial_target_2,
            reason_codes=reason_codes,
            confidence=0.75,
        )
    return None
