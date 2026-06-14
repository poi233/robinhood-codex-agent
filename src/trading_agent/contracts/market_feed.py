from __future__ import annotations


def validate_market_feed_manifest(payload: dict[str, object]) -> None:
    required = {
        "date",
        "run_mode",
        "requested_symbols",
        "completed_symbols",
        "failed_symbols",
        "timeframes",
        "data_status",
        "sources",
    }
    missing = required - set(payload)
    if missing:
        raise ValueError(f"missing market feed keys: {sorted(missing)}")
