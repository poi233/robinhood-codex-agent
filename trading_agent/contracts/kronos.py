from __future__ import annotations

REQUIRED_KEYS = {
    "date",
    "generated_at",
    "timeframe",
    "horizon_bars",
    "source_universe",
    "model",
    "data_status",
    "symbols",
    "notes",
}


def validate_kronos_payload(payload: dict[str, object]) -> None:
    missing = REQUIRED_KEYS - set(payload)
    if missing:
        raise ValueError(f"missing kronos keys: {sorted(missing)}")
    if payload["data_status"] not in {"ok", "partial", "failed", "stale"}:
        raise ValueError("invalid kronos data_status")
