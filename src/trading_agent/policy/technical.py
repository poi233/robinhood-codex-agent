from __future__ import annotations

from typing import Any

from trading_agent.policy.models import PolicyInputs


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
