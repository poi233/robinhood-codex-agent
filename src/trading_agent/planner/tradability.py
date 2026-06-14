from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import read_json, write_json
from trading_agent.core.time import PT


def _selected_symbols(candidate_snapshot: dict[str, Any]) -> list[str]:
    symbols: list[str] = []
    for symbol in candidate_snapshot.get("selected_symbols", []):
        normalized = str(symbol or "").upper().strip()
        if normalized and normalized not in symbols:
            symbols.append(normalized)
    return symbols


def build_tradability_snapshot(
    *,
    run_date: str,
    candidate_snapshot: dict[str, Any],
    account_snapshot: dict[str, Any],
    quote_snapshot: dict[str, Any],
) -> dict[str, Any]:
    symbols = _selected_symbols(candidate_snapshot)
    account_ok = account_snapshot.get("agentic_account_identified") is True and account_snapshot.get("data_status", "ok") != "failed"
    quote_symbols = quote_snapshot.get("symbols") if isinstance(quote_snapshot.get("symbols"), dict) else {}
    payload_symbols: dict[str, Any] = {}
    untradable: list[str] = []

    for symbol in symbols:
        has_quote = symbol in quote_symbols and float((quote_symbols.get(symbol) or {}).get("last_price") or 0) > 0
        tradable = bool(account_ok and has_quote)
        if not tradable:
            untradable.append(symbol)
        reason = "deterministic local checks passed" if tradable else "missing account identification or local quote"
        payload_symbols[symbol] = {
            "tradable": tradable,
            "fractional_tradable": tradable,
            "regular_hours": True,
            "reason": reason,
            "source": "local_account_and_quote_snapshot",
        }

    if not account_ok:
        data_status = "failed"
    elif untradable and payload_symbols:
        data_status = "partial"
    else:
        data_status = "ok"
    return {
        "date": run_date,
        "generated_at": datetime.now(tz=PT).isoformat(),
        "data_status": data_status,
        "symbols": payload_symbols,
        "untradable_symbols": untradable,
        "notes": "Deterministic local tradability gate; broker-level tradability prompt is no longer used for candidate plumbing.",
    }


def build_tradability_snapshot_from_paths(agent_root: Path, run_date: str) -> dict[str, Any]:
    paths = build_runtime_paths(agent_root, run_date=run_date)
    candidate_snapshot = read_json(paths.candidate_snapshot_path) if paths.candidate_snapshot_path.exists() else {}
    account_snapshot = read_json(paths.account_snapshot_path) if paths.account_snapshot_path.exists() else {}
    quote_snapshot = read_json(paths.quote_snapshot_candidates_path) if paths.quote_snapshot_candidates_path.exists() else {}
    payload = build_tradability_snapshot(
        run_date=run_date,
        candidate_snapshot=candidate_snapshot if isinstance(candidate_snapshot, dict) else {},
        account_snapshot=account_snapshot if isinstance(account_snapshot, dict) else {},
        quote_snapshot=quote_snapshot if isinstance(quote_snapshot, dict) else {},
    )
    write_json(paths.tradability_snapshot_path, payload)
    return payload

