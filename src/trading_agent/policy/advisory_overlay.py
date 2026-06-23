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
        "fundamental": _fresh_payload(paths.signals_dir / "fundamental_snapshot.json", run_date),
        "event": _fresh_payload(paths.planner_dir / "event_snapshot.json", run_date),
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
    # ai_signals layers are LISTS of canonical envelopes ({symbol, direction, confidence, ...}),
    # not dicts keyed by symbol.
    for layer in ((artifacts.get("ai_signals") or {}).get("layers") or {}).values():
        if isinstance(layer, list):
            for env in layer:
                if isinstance(env, dict) and env.get("symbol"):
                    symbols.add(str(env["symbol"]).upper())
    position_weights = (artifacts.get("portfolio_target") or {}).get("position_weights") or {}
    symbols.update(str(symbol).upper() for symbol in position_weights if symbol)
    theme_by_symbol = (artifacts.get("portfolio_target") or {}).get("theme_by_symbol") or {}
    symbols.update(str(symbol).upper() for symbol in theme_by_symbol if symbol)
    for layer in ("fundamental", "event"):
        layer_symbols = (artifacts.get(layer) or {}).get("symbols") or {}
        symbols.update(str(symbol).upper() for symbol in layer_symbols if symbol)
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
    # ai_signals layers are LISTS of canonical envelopes ({symbol, direction,
    # confidence, ...}), one list per layer (dsa/kronos/catalyst) — NOT dicts
    # keyed by symbol. Match the envelope whose symbol equals this candidate.
    layers = (artifacts.get("ai_signals") or {}).get("layers") or {}
    normalized = str(symbol).upper()
    result: dict[str, Any] = {}
    for layer_name, layer in layers.items():
        if not isinstance(layer, list):
            continue
        for env in layer:
            if not isinstance(env, dict) or str(env.get("symbol") or "").upper() != normalized:
                continue
            result[str(layer_name)] = {
                "direction": env.get("direction"),
                "confidence": env.get("confidence"),
                "reason_codes": list(env.get("reason_codes") or []),
                "warning_codes": list(env.get("warning_codes") or []),
            }
            break
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


def _fundamental_component(artifacts: dict[str, dict[str, Any]], symbol: str) -> dict[str, Any]:
    payload = (((artifacts.get("fundamental") or {}).get("symbols") or {}).get(symbol) or {})
    if not isinstance(payload, dict) or not payload:
        return {}
    return {
        "quality_flags": list(payload.get("quality_flags") or []),
        "suggested_use": payload.get("suggested_use"),
    }


def _event_component(artifacts: dict[str, dict[str, Any]], symbol: str) -> dict[str, Any]:
    payload = (((artifacts.get("event") or {}).get("symbols") or {}).get(symbol) or {})
    if not isinstance(payload, dict) or not payload:
        return {}
    return {
        "event_flags": list(payload.get("event_flags") or []),
        "days_to_earnings": payload.get("days_to_earnings"),
    }


def _fundamental_rank_delta(component: dict[str, Any]) -> tuple[float, list[str]]:
    # Quality is a caution filter only: weak fundamentals can demote, never promote.
    if component.get("quality_flags"):
        return -2.0, ["fundamental_quality_warning"]
    return 0.0, []


def _event_rank_delta(component: dict[str, Any]) -> tuple[float, list[str]]:
    flags = set(component.get("event_flags") or [])
    delta = 0.0
    reasons: list[str] = []
    if "earnings_imminent" in flags:
        delta -= 2.0
        reasons.append("earnings_imminent_caution")
    if {"estimate_revised_up", "analyst_bullish"} & flags:
        delta += 2.0
        reasons.append("event_estimate_up")
    if {"estimate_revised_down", "analyst_bearish"} & flags:
        delta -= 2.0
        reasons.append("event_estimate_down")
    return delta, reasons


def _factor_rank_delta(component: dict[str, Any]) -> tuple[float, list[str]]:
    score = component.get("score")
    if not isinstance(score, (int, float)):
        return 0.0, []
    if score >= 80.0:
        return 3.0, ["factor_alpha_high"]
    if score <= 30.0:
        return -3.0, ["factor_alpha_low"]
    return 0.0, []


def _ai_rank_delta(component: dict[str, Any]) -> tuple[float, list[str]]:
    delta = 0.0
    reasons: list[str] = []
    for layer_name, payload in component.items():
        if not isinstance(payload, dict):
            continue
        confidence = payload.get("confidence")
        if not isinstance(confidence, (int, float)) or confidence < 0.70:
            continue
        direction = str(payload.get("direction") or "").lower()
        if direction in {"long", "bullish", "positive", "buy"}:
            delta += 2.0
            reasons.append(f"ai_{layer_name}_bullish")
        elif direction in {"short", "bearish", "negative", "avoid", "sell"}:
            delta -= 2.0
            reasons.append(f"ai_{layer_name}_bearish")
    return delta, reasons


def _risk_tightening(components: dict[str, Any]) -> tuple[bool, float, list[str], list[str]]:
    block_buy = False
    size_multiplier = 1.0
    blocked_reasons: list[str] = []
    reason_codes: list[str] = []

    regime = components.get("regime") or {}
    regime_name = str(regime.get("regime") or "").lower()
    applied_multiplier = regime.get("applied_multiplier")
    if regime_name in {"risk_off", "panic"}:
        block_buy = True
        blocked_reasons.append("regime_blocks_new_buy")
        reason_codes.append("regime_blocks_new_buy")
        size_multiplier = 0.0
    elif isinstance(applied_multiplier, (int, float)):
        clamped = max(0.0, min(1.0, float(applied_multiplier)))
        if clamped < size_multiplier:
            size_multiplier = clamped
            reason_codes.append("regime_size_multiplier")

    portfolio = components.get("portfolio") or {}
    if portfolio.get("oversize_position"):
        block_buy = True
        blocked_reasons.append("portfolio_oversize_position")
        reason_codes.append("portfolio_oversize_position")
    if portfolio.get("overexposed_theme"):
        block_buy = True
        blocked_reasons.append("portfolio_overexposed_theme")
        reason_codes.append("portfolio_overexposed_theme")

    return block_buy, size_multiplier, blocked_reasons, reason_codes


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
            "fundamental": _fundamental_component(artifacts, symbol),
            "event": _event_component(artifacts, symbol),
        }
        factor_delta, factor_reasons = _factor_rank_delta(components["factor_alpha"])
        ai_delta, ai_reasons = _ai_rank_delta(components["ai"])
        fundamental_delta, fundamental_reasons = _fundamental_rank_delta(components["fundamental"])
        event_delta, event_reasons = _event_rank_delta(components["event"])
        block_buy, size_multiplier, blocked_reasons, risk_reasons = _risk_tightening(components)
        reason_codes = [
            source
            for source, value in components.items()
            if value
        ]
        reason_codes.extend(factor_reasons)
        reason_codes.extend(ai_reasons)
        reason_codes.extend(fundamental_reasons)
        reason_codes.extend(event_reasons)
        reason_codes.extend(risk_reasons)
        overlay_symbols[symbol] = SymbolOverlay(
            symbol=symbol,
            rank_delta=max(-5.0, min(5.0, factor_delta + ai_delta + fundamental_delta + event_delta)),
            size_multiplier=size_multiplier,
            block_buy=block_buy,
            blocked_reasons=blocked_reasons,
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
