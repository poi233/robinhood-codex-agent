from __future__ import annotations

from trading_agent.policy.models import OrderIntent, PolicyInputs
from trading_agent.policy.risk import has_open_order
from trading_agent.policy.technical import as_float, technical_symbol_payload


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

        technical = technical_symbol_payload(inputs, symbol)
        if not technical:
            continue

        reason_codes: list[str] = []
        long_setup = technical.get("long_setup") or {}
        short_setup = technical.get("short_setup") or {}
        partial_target_1 = as_float(long_setup.get("target_1"))
        partial_target_2 = as_float(long_setup.get("target_2"))
        if (
            "partial_take_profit" in allowed_actions
            and position.unrealized_return >= 0.025
            and (
                (partial_target_2 is not None and quote.price >= partial_target_2)
                or (partial_target_1 is not None and quote.price >= partial_target_1)
            )
        ):
            reason_codes.append("partial_take_profit")

        trigger_below = as_float(short_setup.get("trigger_below"))
        risk_target_1 = as_float(short_setup.get("target_1"))
        risk_target_2 = as_float(short_setup.get("target_2"))
        if (
            "risk_exit" in allowed_actions
            and short_setup.get("status") in {"active", "watch"}
            and trigger_below is not None
            and quote.price < trigger_below
        ):
            reason_codes.append("risk_exit")

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

        quantity = round(max(0.0, min(position.quantity, position.quantity * sell_fraction)), 8)
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
