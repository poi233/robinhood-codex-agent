from __future__ import annotations


def build_trader_watch_levels(technical_payload: dict[str, object]) -> dict[str, object]:
    symbols = technical_payload.get("symbols", {})
    result: dict[str, object] = {}
    if not isinstance(symbols, dict):
        return result
    for symbol, payload in symbols.items():
        if not isinstance(payload, dict):
            continue
        result[symbol] = {
            "current_context": payload.get("technical_action", "observe"),
            "confidence": payload.get("confidence", "unknown"),
            "key_levels": payload.get("key_levels", {}),
            "long_setup": payload.get("long_setup", {}),
            "risk_reduction_setup": payload.get("short_setup", {}),
            "no_trade_zone": payload.get("no_trade_zone", {}),
        }
    return result
