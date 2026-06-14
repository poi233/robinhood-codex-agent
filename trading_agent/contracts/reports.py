from __future__ import annotations


def validate_report_payload(payload: dict[str, object]) -> None:
    required = {"date", "generated_at", "summary"}
    missing = required - set(payload)
    if missing:
        raise ValueError(f"missing report keys: {sorted(missing)}")
