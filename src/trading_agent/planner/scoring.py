from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import read_json, write_json
from trading_agent.core.time import PT


WEIGHTS = {
    "dsa": 0.35,
    "technical": 0.30,
    "kronos": 0.15,
    "quote": 0.10,
    "catalyst": 0.10,
}


def _read_json_or_empty(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = read_json(path)
    return payload if isinstance(payload, dict) else {}


def _clamp_score(value: Any, default: float = 0.0) -> float:
    try:
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return default


def _symbol_in_values(symbol: str, values: Any) -> bool:
    if not isinstance(values, list):
        return False
    for value in values:
        if isinstance(value, dict):
            candidate = value.get("symbol") or value.get("ticker")
        else:
            candidate = value
        if str(candidate or "").upper() == symbol:
            return True
    return False


def _dsa_component(symbol: str, dsa: dict[str, Any]) -> tuple[float, bool, list[str]]:
    if _symbol_in_values(symbol, dsa.get("blocked_symbols")):
        return 0.0, True, ["dsa_block"]
    for value in dsa.get("selected_candidates") or []:
        if isinstance(value, dict) and str(value.get("symbol") or value.get("ticker") or "").upper() == symbol:
            return _clamp_score(value.get("score"), 70.0), False, []
        if str(value or "").upper() == symbol:
            return 70.0, False, []
    signal = ((dsa.get("symbol_signals") or {}).get(symbol) or {})
    if isinstance(signal, dict):
        if str(signal.get("action") or signal.get("suggested_premarket_use") or "").lower() == "block":
            return 0.0, True, ["dsa_block"]
        return _clamp_score(signal.get("score"), 50.0), False, []
    return 0.0, False, []


def _technical_component(symbol: str, technical: dict[str, Any]) -> float:
    payload = ((technical.get("symbols") or {}).get(symbol) or {})
    if not isinstance(payload, dict):
        return 0.0
    if "priority_score" in payload:
        return _clamp_score(payload.get("priority_score"))
    action = str(payload.get("technical_action") or "").lower()
    return {
        "buy_bias": 80.0,
        "hold": 60.0,
        "observe": 50.0,
        "sell_bias": 30.0,
        "avoid": 20.0,
    }.get(action, 0.0)


def _kronos_component(symbol: str, kronos: dict[str, Any]) -> float:
    payload = ((kronos.get("symbols") or {}).get(symbol) or {})
    if not isinstance(payload, dict):
        return 0.0
    confidence = _clamp_score(payload.get("confidence"), 0.5) / 100.0 if float(payload.get("confidence", 0) or 0) > 1 else float(payload.get("confidence", 0.5) or 0.5)
    bias = str(payload.get("signal") or payload.get("direction_bias") or "").lower()
    setup = str(payload.get("setup_bias") or "").lower()
    if bias in {"bullish", "breakout"} or setup in {"breakout", "pullback"}:
        return _clamp_score(50 + 40 * confidence)
    if bias in {"bearish", "avoid"} or setup == "avoid":
        return _clamp_score(50 - 40 * confidence)
    return 50.0


def _quote_component(symbol: str, quote: dict[str, Any]) -> float:
    payload = ((quote.get("symbols") or {}).get(symbol) or {})
    if not isinstance(payload, dict):
        return 0.0
    change_pct = payload.get("change_pct")
    if change_pct is None and payload.get("last_price") is not None and payload.get("previous_close") is not None:
        try:
            last = float(payload["last_price"])
            previous = float(payload["previous_close"])
            change_pct = ((last - previous) / previous) * 100 if previous else 0
        except (TypeError, ValueError):
            change_pct = 0
    return _clamp_score(50 + float(change_pct or 0) * 5)


def _catalyst_component(symbol: str, catalyst: dict[str, Any]) -> float:
    payload = ((catalyst.get("symbols") or {}).get(symbol) or {})
    if not isinstance(payload, dict):
        return 0.0
    return _clamp_score(payload.get("catalyst_score") or payload.get("score"))


def score_candidate(
    *,
    symbol: str,
    dsa: dict[str, Any],
    kronos: dict[str, Any],
    technical: dict[str, Any],
    quote: dict[str, Any],
    catalyst: dict[str, Any],
) -> dict[str, Any]:
    normalized = symbol.upper()
    dsa_score, blocked, block_reasons = _dsa_component(normalized, dsa)
    components = {
        "dsa": round(dsa_score, 2),
        "technical": round(_technical_component(normalized, technical), 2),
        "kronos": round(_kronos_component(normalized, kronos), 2),
        "quote": round(_quote_component(normalized, quote), 2),
        "catalyst": round(_catalyst_component(normalized, catalyst), 2),
    }
    score = sum(components[key] * WEIGHTS[key] for key in WEIGHTS)
    return {
        "symbol": normalized,
        "score": round(score, 2),
        "components": components,
        "weights": dict(WEIGHTS),
        "blocked": blocked,
        "block_reasons": block_reasons,
    }


def build_candidate_scores_from_paths(agent_root: Path, run_date: str) -> dict[str, Any]:
    paths = build_runtime_paths(agent_root, run_date=run_date)
    candidate_snapshot = _read_json_or_empty(paths.candidate_snapshot_path)
    quote_core = _read_json_or_empty(paths.quote_snapshot_core_path)
    quote_candidates = _read_json_or_empty(paths.quote_snapshot_candidates_path)
    quote = {"symbols": {**(quote_core.get("symbols") or {}), **(quote_candidates.get("symbols") or {})}}
    selected_symbols = [str(symbol).upper() for symbol in candidate_snapshot.get("selected_symbols", [])]

    symbols = {
        symbol: score_candidate(
            symbol=symbol,
            dsa=_read_json_or_empty(paths.dsa_signals_path),
            kronos=_read_json_or_empty(paths.kronos_signals_path),
            technical=_read_json_or_empty(paths.technical_signals_path),
            quote=quote,
            catalyst=_read_json_or_empty(paths.catalyst_snapshot_path),
        )
        for symbol in selected_symbols
    }
    ranked = sorted(symbols, key=lambda item: (symbols[item]["blocked"], -float(symbols[item]["score"]), item))
    payload = {
        "date": run_date,
        "generated_at": datetime.now(tz=PT).isoformat(),
        "weights": dict(WEIGHTS),
        "symbols": symbols,
        "ranked_symbols": ranked,
        "notes": "Deterministic aggregation of existing signal-layer outputs; does not create new AI reasoning.",
    }
    write_json(paths.candidate_scores_path, payload)
    return payload

