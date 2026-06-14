from __future__ import annotations


def validate_daily_plan_payload(payload: dict[str, object]) -> None:
    required = {
        "date",
        "generated_at",
        "market_regime",
        "today_watchlist",
        "symbol_trade_rules",
        "data_status",
    }
    missing = required - set(payload)
    if missing:
        raise ValueError(f"missing daily plan keys: {sorted(missing)}")
