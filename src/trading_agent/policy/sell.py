from __future__ import annotations

from trading_agent.policy.models import OrderIntent, PolicyInputs
from trading_agent.policy.risk import has_open_order


def evaluate_sell(inputs: PolicyInputs) -> OrderIntent | None:
    if not inputs.daily_plan:
        return None
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

        reason_codes: list[str] = []
        if "partial_take_profit" in allowed_actions and position.unrealized_return >= 0.025:
            reason_codes.append("partial_take_profit")

        technical = ((inputs.technical_signals.get("symbols") or {}).get(symbol) or {})
        short_setup = technical.get("short_setup") or {}
        trigger_below = short_setup.get("trigger_below")
        if (
            "risk_exit" in allowed_actions
            and short_setup.get("status") in {"active", "watch"}
            and trigger_below is not None
            and quote.price < float(trigger_below)
        ):
            reason_codes.append("risk_exit")

        if not reason_codes:
            continue

        quantity = round(max(0.0, min(position.quantity, position.quantity / 2)), 8)
        if quantity <= 0:
            continue
        return OrderIntent(
            symbol=symbol,
            side="sell",
            order_type="limit",
            limit_price=quote.price,
            estimated_notional=round(quantity * quote.price, 2),
            quantity=quantity,
            reason_codes=reason_codes,
            confidence=0.75,
        )
    return None
