from __future__ import annotations

from pathlib import Path
from typing import Any

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import read_json, write_json
from trading_agent.data.universe import parse_universe


CORE_MARKET_SYMBOLS = ("SPY", "QQQ", "IWM", "SMH")


def _read_json_or_empty(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = read_json(path)
    return payload if isinstance(payload, dict) else {}


def _append_symbol(symbols: list[str], symbol: object, universe: set[str] | None = None) -> None:
    value = str(symbol or "").upper().strip()
    if not value:
        return
    if universe is not None and value not in universe:
        return
    if value not in symbols:
        symbols.append(value)


def _append_payload_symbols(symbols: list[str], values: object, universe: set[str] | None = None) -> None:
    if not isinstance(values, list):
        return
    for value in values:
        if isinstance(value, dict):
            _append_symbol(symbols, value.get("symbol") or value.get("ticker"), universe)
        else:
            _append_symbol(symbols, value, universe)


def build_candidate_snapshot(agent_root: Path, run_date: str) -> dict[str, Any]:
    paths = build_runtime_paths(agent_root, run_date=run_date)
    universe = set(parse_universe(paths.config_dir / "universe.txt"))
    account = _read_json_or_empty(paths.account_snapshot_path)
    dsa = _read_json_or_empty(paths.dsa_signals_path)
    kronos = _read_json_or_empty(paths.kronos_signals_path)
    technical = _read_json_or_empty(paths.technical_signals_path)

    selected: list[str] = []
    blocked: list[str] = []
    core_symbols: list[str] = []

    for symbol in CORE_MARKET_SYMBOLS:
        _append_symbol(core_symbols, symbol)

    _append_payload_symbols(core_symbols, account.get("current_positions"))
    _append_payload_symbols(core_symbols, account.get("open_orders"))

    _append_payload_symbols(selected, account.get("current_positions"), universe)
    _append_payload_symbols(selected, account.get("open_orders"), universe)
    _append_payload_symbols(selected, dsa.get("selected_candidates"), universe)
    _append_payload_symbols(blocked, dsa.get("blocked_symbols"), universe)

    for symbol in (kronos.get("symbols") or {}).keys():
        _append_symbol(selected, symbol, universe)

    for symbol, payload in (technical.get("symbols") or {}).items():
        if not isinstance(payload, dict):
            continue
        action = str(payload.get("technical_action") or "").lower()
        if action not in {"avoid", "blocked"}:
            _append_symbol(selected, symbol, universe)

    output = {
        "date": run_date,
        "source_universe": str(paths.config_dir / "universe.txt"),
        "core_symbols": core_symbols,
        "selected_symbols": selected[:20],
        "blocked_symbols": blocked,
        "source_status": {
            "account_snapshot": "ok" if paths.account_snapshot_path.exists() else "missing",
            "dsa": "ok" if paths.dsa_signals_path.exists() else "missing",
            "kronos": "ok" if paths.kronos_signals_path.exists() else "missing",
            "technical": "ok" if paths.technical_signals_path.exists() else "missing",
        },
        "notes": "candidate snapshot is deterministic; final planner decides trade permissions",
    }
    write_json(paths.candidate_snapshot_path, output)
    return output
