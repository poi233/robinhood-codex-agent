from __future__ import annotations

from trading_agent.policy.models import PolicyInputs


def watchlist_symbols(inputs: PolicyInputs) -> list[str]:
    if not inputs.daily_plan:
        return []
    symbols = []
    for symbol in inputs.daily_plan.get("today_watchlist", []):
        normalized = str(symbol).upper()
        if normalized not in symbols:
            symbols.append(normalized)
    return symbols


def eligible_symbols(inputs: PolicyInputs) -> list[str]:
    universe = {symbol.upper() for symbol in inputs.universe}
    allowlist = {symbol.upper() for symbol in inputs.today_allowlist}
    return [symbol for symbol in watchlist_symbols(inputs) if symbol in universe and symbol in allowlist]


def has_open_order(inputs: PolicyInputs, symbol: str) -> bool:
    return any(order.symbol.upper() == symbol.upper() and order.status.lower() in {"open", "queued", "pending"} for order in inputs.open_orders)


def daily_notional_remaining(inputs: PolicyInputs) -> float:
    max_daily = float(inputs.risk_caps.get("max_daily_notional", 0) or 0)
    used = float(inputs.daily_usage.get("used_notional", 0) or 0)
    return max(0.0, max_daily - used)


def single_order_cap(inputs: PolicyInputs, symbol: str) -> float:
    cap = float(inputs.risk_caps.get("max_single_order_notional", 0) or 0)
    if inputs.daily_plan:
        rule = (inputs.daily_plan.get("symbol_trade_rules") or {}).get(symbol) or {}
        if "max_notional" in rule:
            cap = min(cap, float(rule["max_notional"]))
    return max(0.0, cap)


def losing_position_exists(inputs: PolicyInputs, symbol: str) -> bool:
    position = inputs.positions.get(symbol.upper())
    return bool(position and position.quantity > 0 and position.unrealized_return < 0)


def quote_is_tradeable(inputs: PolicyInputs, symbol: str) -> bool:
    quote = inputs.quotes.get(symbol.upper())
    return bool(quote and quote.is_fresh and quote.price > 0)
