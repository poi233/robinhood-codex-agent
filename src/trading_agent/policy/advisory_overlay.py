from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SymbolOverlay:
    symbol: str
    rank_delta: float = 0.0
    size_multiplier: float = 1.0
    block_buy: bool = False
    blocked_reasons: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    components: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AdvisoryOverlay:
    run_date: str
    symbols: dict[str, SymbolOverlay] = field(default_factory=dict)
    sources: dict[str, bool] = field(default_factory=dict)


def _read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _payload_date(payload: dict[str, Any]) -> str | None:
    for key in ("date", "asof_date", "as_of"):
        value = payload.get(key)
        if value:
            return str(value)
    return None


def _fresh_payload(path: Path, run_date: str) -> dict[str, Any]:
    payload = _read_json_if_exists(path)
    if not payload:
        return {}
    payload_date = _payload_date(payload)
    if payload_date is not None and payload_date != run_date:
        return {}
    return payload


def load_advisory_artifacts(paths: Any) -> dict[str, dict[str, Any]]:
    """Read M-stage advisory artifacts without throwing.

    Missing files, stale dated payloads, malformed JSON, and non-dict payloads all
    degrade to empty dicts so enabling the loader cannot break intraday.
    """

    run_date = str(paths.run_date)
    return {
        "factor_alpha": _fresh_payload(paths.factor_alpha_path, run_date),
        "ai_signals": _fresh_payload(paths.ai_signals_path, run_date),
        "regime_state": _fresh_payload(paths.planner_dir / "regime_state.json", run_date),
        "portfolio_target": _fresh_payload(paths.planner_dir / "portfolio_target.json", run_date),
    }


def _symbols_from_inputs(inputs: Any) -> set[str]:
    symbols: set[str] = set()
    for symbol in getattr(inputs, "today_allowlist", []) or []:
        if symbol:
            symbols.add(str(symbol).upper())
    for collection in ("candidate_scores", "factor_alpha"):
        payload = getattr(inputs, collection, None)
        if isinstance(payload, dict):
            symbols.update(str(symbol).upper() for symbol in (payload.get("symbols") or {}) if symbol)
    return symbols


def _symbols_from_artifacts(artifacts: dict[str, dict[str, Any]]) -> set[str]:
    symbols: set[str] = set()
    factor_symbols = (artifacts.get("factor_alpha") or {}).get("symbols") or {}
    symbols.update(str(symbol).upper() for symbol in factor_symbols if symbol)
    for layer in ((artifacts.get("ai_signals") or {}).get("layers") or {}).values():
        if isinstance(layer, dict):
            symbols.update(str(symbol).upper() for symbol in (layer.get("symbols") or {}) if symbol)
    position_weights = (artifacts.get("portfolio_target") or {}).get("position_weights") or {}
    symbols.update(str(symbol).upper() for symbol in position_weights if symbol)
    theme_by_symbol = (artifacts.get("portfolio_target") or {}).get("theme_by_symbol") or {}
    symbols.update(str(symbol).upper() for symbol in theme_by_symbol if symbol)
    return symbols


def _factor_component(artifacts: dict[str, dict[str, Any]], symbol: str) -> dict[str, Any]:
    payload = (((artifacts.get("factor_alpha") or {}).get("symbols") or {}).get(symbol) or {})
    if not isinstance(payload, dict):
        return {}
    if not payload:
        return {}
    return {
        "score": payload.get("factor_alpha_score"),
        "factor_components": dict(payload.get("factor_components") or {}),
        "risk_flags": list(payload.get("risk_flags") or []),
    }


def _ai_component(artifacts: dict[str, dict[str, Any]], symbol: str) -> dict[str, Any]:
    layers = (artifacts.get("ai_signals") or {}).get("layers") or {}
    result: dict[str, Any] = {}
    for layer_name, layer in layers.items():
        if not isinstance(layer, dict):
            continue
        symbol_payload = ((layer.get("symbols") or {}).get(symbol) or {})
        if isinstance(symbol_payload, dict) and symbol_payload:
            result[str(layer_name)] = {
                "direction": symbol_payload.get("direction"),
                "confidence": symbol_payload.get("confidence"),
                "reason_codes": list(symbol_payload.get("reason_codes") or []),
                "warning_codes": list(symbol_payload.get("warning_codes") or []),
            }
    return result


def _regime_component(artifacts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    payload = artifacts.get("regime_state") or {}
    if not payload:
        return {}
    return {
        "regime": payload.get("regime"),
        "applied_multiplier": payload.get("applied_multiplier"),
        "reasons": list(payload.get("reasons") or []),
    }


def _portfolio_component(artifacts: dict[str, dict[str, Any]], symbol: str) -> dict[str, Any]:
    payload = artifacts.get("portfolio_target") or {}
    if not payload:
        return {}
    breaches = payload.get("breaches") or {}
    theme = (payload.get("theme_by_symbol") or {}).get(symbol)
    return {
        "position_weight": (payload.get("position_weights") or {}).get(symbol),
        "theme": theme,
        "oversize_position": symbol in set(breaches.get("oversize_positions") or []),
        "overexposed_theme": theme in set(breaches.get("overexposed_themes") or []),
    }


def build_advisory_overlay(inputs: Any, artifacts: dict[str, dict[str, Any]]) -> AdvisoryOverlay:
    run_date = str(getattr(inputs, "run_date", ""))
    symbols = _symbols_from_inputs(inputs) | _symbols_from_artifacts(artifacts)
    regime = _regime_component(artifacts)
    overlay_symbols: dict[str, SymbolOverlay] = {}
    for symbol in sorted(symbols):
        components = {
            "factor_alpha": _factor_component(artifacts, symbol),
            "ai": _ai_component(artifacts, symbol),
            "regime": regime,
            "portfolio": _portfolio_component(artifacts, symbol),
        }
        reason_codes = [
            source
            for source, value in components.items()
            if value
        ]
        overlay_symbols[symbol] = SymbolOverlay(
            symbol=symbol,
            reason_codes=reason_codes,
            components=components,
        )
    return AdvisoryOverlay(
        run_date=run_date,
        symbols=overlay_symbols,
        sources={name: bool(payload) for name, payload in artifacts.items()},
    )


def overlay_for_symbol(overlay: AdvisoryOverlay | None, symbol: str) -> SymbolOverlay:
    normalized = str(symbol).upper()
    if overlay is None:
        return SymbolOverlay(symbol=normalized)
    return overlay.symbols.get(normalized, SymbolOverlay(symbol=normalized))


def symbol_overlay_to_dict(overlay: SymbolOverlay | None) -> dict[str, Any]:
    if overlay is None:
        return {}
    return asdict(overlay)
