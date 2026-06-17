from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from trading_agent.analyzers.ai_signal_schema import (
    normalize_catalyst_signal,
    normalize_dsa_signal,
    normalize_kronos_signal,
    validate_ai_signal,
)
from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import read_json, write_json

# Each layer: (artifact path attr, normalizer). The normalizer maps one symbol's raw signal into the
# canonical envelope. Adding a new AI layer = one line here + one normalizer (the same extensibility
# discipline as the factor registry).
Normalizer = Callable[[str, dict[str, Any], str], dict[str, Any]]


def _symbols_block(payload: Any, key: str = "symbols") -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    block = payload.get(key)
    return block if isinstance(block, dict) else {}


def _normalize_layer(symbols: dict[str, Any], normalizer, *, asof_date: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (valid_envelopes, invalid_records). Invalid records keep their errors so the report
    surfaces contract drift instead of silently dropping a layer."""
    valid: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    for symbol, raw in symbols.items():
        if not isinstance(raw, dict):
            continue
        env = normalizer(str(symbol), raw, asof_date=asof_date)
        errors = validate_ai_signal(env)
        if errors:
            invalid.append({"symbol": str(symbol).upper(), "errors": errors})
        else:
            valid.append(env)
    valid.sort(key=lambda e: e["symbol"])
    return valid, invalid


def build_ai_signal_layer(agent_root: Path, run_date: str) -> dict[str, Any]:
    """Read the DSA / Kronos / Catalyst artifacts, normalize every per-symbol signal into the canonical
    envelope, validate, and assemble the unified `ai_signals.json` payload. Pure read + transform;
    writes nothing. Missing artifacts degrade to empty layers (no crash)."""
    paths = build_runtime_paths(agent_root, run_date=run_date)

    dsa_payload = read_json(paths.dsa_signals_path) if paths.dsa_signals_path.exists() else {}
    kronos_payload = read_json(paths.kronos_signals_path) if paths.kronos_signals_path.exists() else {}
    catalyst_payload = read_json(paths.catalyst_snapshot_path) if paths.catalyst_snapshot_path.exists() else {}

    # asof_date is the run_date (point-in-time): these signals describe the market as known on run_date.
    asof_date = run_date

    dsa_valid, dsa_invalid = _normalize_layer(_symbols_block(dsa_payload, "symbol_signals"), normalize_dsa_signal, asof_date=asof_date)
    kronos_valid, kronos_invalid = _normalize_layer(_symbols_block(kronos_payload), normalize_kronos_signal, asof_date=asof_date)
    catalyst_valid, catalyst_invalid = _normalize_layer(_symbols_block(catalyst_payload), normalize_catalyst_signal, asof_date=asof_date)

    layers = {
        "dsa": dsa_valid,
        "kronos": kronos_valid,
        "catalyst": catalyst_valid,
    }
    invalid = {
        "dsa": dsa_invalid,
        "kronos": kronos_invalid,
        "catalyst": catalyst_invalid,
    }
    total_valid = sum(len(v) for v in layers.values())
    total_invalid = sum(len(v) for v in invalid.values())

    return {
        "date": run_date,
        "asof_date": asof_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": 1,
        "layers": layers,
        "validation": {
            "valid_count": total_valid,
            "invalid_count": total_invalid,
            "invalid": {k: v for k, v in invalid.items() if v},
        },
        "notes": "Standardized AI-signal envelopes (H3): write-only advisory; does not feed champion scoring.",
    }


def build_and_write_ai_signal_layer(agent_root: Path, run_date: str) -> Path:
    payload = build_ai_signal_layer(agent_root, run_date)
    paths = build_runtime_paths(agent_root, run_date=run_date)
    write_json(paths.ai_signals_path, payload)
    return paths.ai_signals_path
