from __future__ import annotations


def validate_technical_payload(payload: dict[str, object]) -> None:
    if "symbols" not in payload:
        raise ValueError("technical payload missing symbols")
    if not isinstance(payload["symbols"], dict):
        raise ValueError("technical symbols must be a mapping")
