from __future__ import annotations

from typing import Any

from trading_agent.policy.models import PolicyInputs


def estimate_price_setup_score(inputs: PolicyInputs, symbol: str) -> float:
    """Score 0-100 for how well price is positioned for a trade setup.

    Computed at ranking time using the same watch levels as decide_buy_price,
    so setup quality influences candidate order before the full price decision runs.
    Weights pending calibration via replay component attribution.

    0   = hard-blocked (no_trade_zone, chasing, no data)
    20  = outside entry zone and no breakout (marginal)
    60+ = breakout setup present; +RR bonus up to 90
    70+ = pullback in entry zone; +RR bonus up to 100
    """
    watch = ((inputs.trader_watch_levels.get("symbols") or {}).get(symbol) or {})
    quote = inputs.quotes.get(symbol)
    if not quote or quote.price <= 0 or not watch:
        return 0.0

    price = quote.price
    entry_low = as_float(watch.get("entry_low"))
    entry_high = as_float(watch.get("entry_high"))
    trigger_above = as_float(watch.get("buy_trigger_above"))
    do_not_chase_above = as_float(watch.get("do_not_chase_above"))
    no_trade_low = as_float(watch.get("no_trade_low"))
    no_trade_high = as_float(watch.get("no_trade_high"))
    stop_price = as_float(watch.get("invalidation_below"))
    target_1 = as_float(watch.get("target_1"))

    if price_in_zone(price, no_trade_low, no_trade_high):
        return 0.0
    if do_not_chase_above is not None and price > do_not_chase_above:
        return 0.0

    in_entry = price_in_zone(price, entry_low, entry_high)
    breakout = trigger_above is not None and price >= trigger_above

    if not in_entry and not breakout:
        return 20.0

    rr_bonus = 0.0
    if stop_price is not None and target_1 is not None and stop_price < price < target_1:
        rr = (target_1 - price) / (price - stop_price)
        # RR 1.5 → 0 bonus; RR 3.0 → 30 bonus; capped at 30
        rr_bonus = min(30.0, max(0.0, (rr - 1.5) * 20.0))

    if in_entry:
        return min(100.0, 70.0 + rr_bonus)
    return min(90.0, 60.0 + rr_bonus)


def as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def technical_symbol_payload(inputs: PolicyInputs, symbol: str) -> dict[str, Any]:
    payload = ((inputs.technical_signals.get("symbols") or {}).get(symbol.upper()) or {})
    return payload if isinstance(payload, dict) else {}


def entry_zone(payload: dict[str, Any], setup_key: str) -> tuple[float | None, float | None]:
    setup = payload.get(setup_key) or {}
    zone = setup.get("entry_zone") or {}
    low = as_float(zone.get("low"))
    high = as_float(zone.get("high"))
    if low is not None and high is not None and low > high:
        low, high = high, low
    return low, high


def price_in_zone(price: float, low: float | None, high: float | None) -> bool:
    if low is None or high is None:
        return False
    return low <= price <= high
