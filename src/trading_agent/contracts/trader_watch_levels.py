from __future__ import annotations

from typing import Any


def validate_trader_watch_levels(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != 1:
        raise ValueError("trader watch levels schema_version must be 1")
    symbols = payload.get("symbols")
    if not isinstance(symbols, dict):
        raise ValueError("trader watch levels symbols must be a mapping")
    for symbol, levels in symbols.items():
        if not isinstance(symbol, str) or not symbol:
            raise ValueError("trader watch levels symbol keys must be non-empty strings")
        if not isinstance(levels, dict):
            raise ValueError(f"trader watch levels for {symbol} must be a mapping")

