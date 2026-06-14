from __future__ import annotations

from typing import Any


def _as_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _risk_reduction_only(short_setup: dict[str, Any]) -> bool:
    notes = str(short_setup.get("notes") or "").lower()
    return "existing-long risk management only" in notes or "never permission to open a short" in notes


def build_trader_watch_levels(technical_payload: dict[str, Any]) -> dict[str, Any]:
    symbols = technical_payload.get("symbols", {})
    result: dict[str, Any] = {"schema_version": 1, "symbols": {}}
    if not isinstance(symbols, dict):
        return result

    for symbol, payload in symbols.items():
        if not isinstance(symbol, str) or not isinstance(payload, dict):
            continue
        key_levels = _as_mapping(payload.get("key_levels"))
        long_setup = _as_mapping(payload.get("long_setup"))
        short_setup = _as_mapping(payload.get("short_setup"))
        no_trade_zone = _as_mapping(payload.get("no_trade_zone"))
        entry_zone = _as_mapping(long_setup.get("entry_zone"))

        result["symbols"][symbol] = {
            "current_context": payload.get("technical_action", "observe"),
            "confidence": payload.get("confidence"),
            "reference_price": key_levels.get("reference_price"),
            "range_low": key_levels.get("range_low"),
            "range_high": key_levels.get("range_high"),
            "supports": _as_list(key_levels.get("supports")),
            "resistances": _as_list(key_levels.get("resistances")),
            "buy_trigger_above": long_setup.get("trigger_above"),
            "entry_low": entry_zone.get("low"),
            "entry_high": entry_zone.get("high"),
            "invalidation_below": long_setup.get("invalidation_below"),
            "target_1": long_setup.get("target_1"),
            "target_2": long_setup.get("target_2"),
            "do_not_chase_above": long_setup.get("do_not_chase_above"),
            "long_status": long_setup.get("status"),
            "long_setup_type": long_setup.get("setup_type"),
            "no_trade_low": no_trade_zone.get("low"),
            "no_trade_high": no_trade_zone.get("high"),
            "no_trade_reason": no_trade_zone.get("reason"),
            "risk_reduction_trigger_below": short_setup.get("trigger_below"),
            "risk_reduction_invalidation_above": short_setup.get("invalidation_above"),
            "risk_reduction_target_1": short_setup.get("target_1"),
            "risk_reduction_target_2": short_setup.get("target_2"),
            "risk_reduction_only": _risk_reduction_only(short_setup),
            "risk_reduction_notes": short_setup.get("notes"),
        }
    return result

