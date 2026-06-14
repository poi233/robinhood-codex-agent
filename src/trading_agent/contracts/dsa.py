from __future__ import annotations


def validate_dsa_payload(payload: dict[str, object]) -> None:
    required = {
        "date",
        "generated_at",
        "source",
        "data_status",
        "market_phase",
        "selected_candidates",
        "blocked_symbols",
        "symbol_signals",
        "notes",
    }
    missing = required - set(payload)
    if missing:
        raise ValueError(f"missing dsa keys: {sorted(missing)}")
