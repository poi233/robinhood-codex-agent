from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import read_json, write_json
from trading_agent.core.time import PT
from trading_agent.planner.scoring_profiles import load_scoring_profile


WEIGHTS = {
    "dsa": 0.25,
    "technical": 0.30,
    "kronos": 0.15,
    "quote": 0.10,
    "catalyst": 0.20,
}

TECHNICAL_ACTION_SCORES = {
    "strong_promote": 90.0,
    "promote": 82.0,
    "buy_bias": 78.0,
    "hold": 60.0,
    "observe": 50.0,
    "neutral": 50.0,
    "reduce": 30.0,
    "sell_bias": 25.0,
    "avoid": 5.0,
    "block": 0.0,
}

NEGATIVE_CATALYST_BIASES = {"negative", "bearish", "reduce", "sell_bias"}
BLOCKING_CATALYST_BIASES = {"block", "avoid"}
MIN_EFFECTIVE_COVERAGE = 0.5


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


def _normalized_confidence(value: Any, default: float = 0.5) -> float:
    try:
        if value is None or value == "":
            return default
        parsed = float(value)
        if parsed > 1:
            parsed = parsed / 100.0
        return max(0.0, min(1.0, parsed))
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
    if isinstance(signal, dict) and signal:
        if str(signal.get("action") or signal.get("suggested_premarket_use") or "").lower() == "block":
            return 0.0, True, ["dsa_block"]
        return _clamp_score(signal.get("score"), 50.0), False, []
    return 0.0, False, []


def _component_result(
    *,
    name: str,
    score: float,
    available: bool,
    confidence: float,
    blocked: bool = False,
    reason: str = "ok",
    weight: float | None = None,
    extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base_weight = WEIGHTS[name] if weight is None else weight
    bounded_confidence = max(0.0, min(1.0, confidence))
    effective_weight = round(base_weight * bounded_confidence, 4) if available else 0.0
    contribution = round(score * effective_weight, 2)
    payload = {
        "score": round(score, 2),
        "available": available,
        "confidence": round(bounded_confidence, 4),
        "blocked": blocked,
        "reason": reason,
        "weight": base_weight,
        "effective_weight": effective_weight,
        "contribution": contribution,
        # Backward-compatible aliases used by existing tests and local diagnostics readers.
        "component_score": round(score, 2),
        "component_weight": base_weight,
        "weighted_contribution": contribution,
    }
    if extras:
        payload.update(extras)
    return payload


def _dsa_diagnostic(symbol: str, dsa: dict[str, Any]) -> tuple[float, dict[str, Any], list[str]]:
    score, blocked, block_reasons = _dsa_component(symbol, dsa)
    if blocked:
        return 0.0, _component_result(
            name="dsa",
            score=0.0,
            available=True,
            confidence=1.0,
            blocked=True,
            reason="dsa_block",
        ), block_reasons
    if score > 0:
        return score, _component_result(
            name="dsa",
            score=score,
            available=True,
            confidence=1.0,
            reason="ok",
        ), []
    return 50.0, _component_result(
        name="dsa",
        score=50.0,
        available=False,
        confidence=0.0,
        reason="dsa_unavailable",
    ), []


def _dsa_overlap_flags(symbol: str, dsa: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    signal = ((dsa.get("symbol_signals") or {}).get(symbol) or {})
    if not isinstance(signal, dict):
        return flags
    strategy_matches = {str(value).lower() for value in signal.get("strategy_matches") or []}
    setup = str(signal.get("setup") or "").lower()
    combined_text = " ".join(
        str(value)
        for value in [
            signal.get("evidence_summary"),
            signal.get("relative_strength_context"),
            *list(signal.get("risk_flags") or []),
            *list(signal.get("reject_reasons") or []),
        ]
        if value
    ).lower()
    if setup in {"breakout", "pullback", "reclaim"} or "bull_trend" in strategy_matches or "volume_breakout" in strategy_matches:
        flags.append("dsa_mentions_technical_trend")
    catalyst_terms = ("earnings", "guidance", "contract", "launch", "news", "catalyst", "investor day", "regulatory")
    if "event_driven" in strategy_matches or any(term in combined_text for term in catalyst_terms):
        flags.append("dsa_mentions_news_catalyst")
    return flags


def _technical_action_payload(payload: dict[str, Any]) -> tuple[str, str | None, str | None]:
    raw_value: str | None = None
    raw_field: str | None = None
    for field in ("technical_action", "action", "bias", "recommendation"):
        value = payload.get(field)
        if value is None or value == "":
            continue
        raw_value = str(value).strip().lower()
        raw_field = field
        break
    if raw_value is None:
        return "observe", None, None
    normalized = raw_value if raw_value in TECHNICAL_ACTION_SCORES else "observe"
    return normalized, raw_value, raw_field


def _technical_component(symbol: str, technical: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    payload = ((technical.get("symbols") or {}).get(symbol) or {})
    if not isinstance(payload, dict) or not payload:
        return 50.0, _component_result(
            name="technical",
            score=50.0,
            available=False,
            confidence=0.0,
            reason="technical_payload_missing",
            extras={
                "raw_action": None,
                "normalized_action": None,
                "action_field": None,
                "warning": "technical_payload_missing",
            },
        )
    if "priority_score" in payload:
        score = _clamp_score(payload.get("priority_score"))
        normalized_action, raw_action, raw_field = _technical_action_payload(payload)
        warning = None
        if raw_action and raw_action not in TECHNICAL_ACTION_SCORES:
            warning = f"unmapped_technical_action:{raw_action}"
        blocked = normalized_action == "block"
        reason = "technical_block" if blocked else "ok"
        return score, _component_result(
            name="technical",
            score=score,
            available=True,
            confidence=1.0,
            blocked=blocked,
            reason=reason,
            extras={
                "raw_action": raw_action,
                "normalized_action": normalized_action,
                "action_field": raw_field,
                "warning": warning,
            },
        )
    normalized_action, raw_action, raw_field = _technical_action_payload(payload)
    score = TECHNICAL_ACTION_SCORES[normalized_action]
    warning = None
    if raw_action and raw_action not in TECHNICAL_ACTION_SCORES:
        warning = f"unmapped_technical_action:{raw_action}"
    blocked = normalized_action == "block"
    reason = "technical_block" if blocked else "ok"
    return score, _component_result(
        name="technical",
        score=score,
        available=True,
        confidence=1.0,
        blocked=blocked,
        reason=reason,
        extras={
            "raw_action": raw_action,
            "normalized_action": normalized_action,
            "action_field": raw_field,
            "warning": warning,
        },
    )


def _kronos_component(symbol: str, kronos: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    payload = ((kronos.get("symbols") or {}).get(symbol) or {})
    if not isinstance(payload, dict) or not payload:
        return 50.0, _component_result(
            name="kronos",
            score=50.0,
            available=False,
            confidence=0.0,
            reason="kronos_unavailable",
        )
    confidence = _normalized_confidence(payload.get("confidence"), 0.5)
    bias = str(payload.get("signal") or payload.get("direction_bias") or "").lower()
    setup = str(payload.get("setup_bias") or "").lower()
    if bias in {"bullish", "breakout"} or setup in {"breakout", "pullback"}:
        score = _clamp_score(50 + 40 * confidence)
        return score, _component_result(
            name="kronos",
            score=score,
            available=True,
            confidence=confidence,
            reason="ok",
            extras={"bias": bias or None, "setup_bias": setup or None},
        )
    if bias in {"bearish", "avoid"} or setup == "avoid":
        score = _clamp_score(50 - 40 * confidence)
        return score, _component_result(
            name="kronos",
            score=score,
            available=True,
            confidence=confidence,
            blocked=False,
            reason="kronos_bearish" if bias == "bearish" or setup == "avoid" else "ok",
            extras={"bias": bias or None, "setup_bias": setup or None},
        )
    return 50.0, _component_result(
        name="kronos",
        score=50.0,
        available=True,
        confidence=confidence,
        reason="ok",
        extras={"bias": bias or None, "setup_bias": setup or None},
    )


def _quote_component(symbol: str, quote: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    payload = ((quote.get("symbols") or {}).get(symbol) or {})
    if not isinstance(payload, dict):
        return 50.0, _component_result(
            name="quote",
            score=50.0,
            available=False,
            confidence=0.0,
            reason="quote_unavailable",
        )
    change_pct = payload.get("change_pct")
    if change_pct is None and payload.get("last_price") is not None and payload.get("previous_close") is not None:
        try:
            last = float(payload["last_price"])
            previous = float(payload["previous_close"])
            change_pct = ((last - previous) / previous) * 100 if previous else 0
        except (TypeError, ValueError):
            change_pct = 0
    score = _clamp_score(payload.get("score"), None)
    if score is None:
        score = _clamp_score(50 + float(change_pct or 0) * 5)
    return score, _component_result(
        name="quote",
        score=score,
        available=True,
        confidence=1.0,
        reason="ok",
        extras={"change_pct": _clamp_score(change_pct, 0.0) if change_pct is not None else None},
    )


def _catalyst_component(symbol: str, catalyst: dict[str, Any]) -> float:
    payload = ((catalyst.get("symbols") or {}).get(symbol) or {})
    if not isinstance(payload, dict):
        return 50.0, _component_result(
            name="catalyst",
            score=50.0,
            available=False,
            confidence=0.0,
            reason="catalyst_unavailable",
            extras={"status": None, "catalyst_bias": None, "missing_numeric_score": False},
        )

    block_reasons = payload.get("block_reasons") or []
    catalyst_bias = str(payload.get("catalyst_bias") or "").strip().lower()
    event_risk = str(payload.get("event_risk") or payload.get("earnings_risk") or "").strip().lower()
    negative_catalysts = payload.get("negative_catalysts") or payload.get("risk_flags") or []
    positive_catalysts = payload.get("positive_catalysts") or payload.get("catalysts") or []
    confidence = _normalized_confidence(payload.get("confidence"), 0.5)
    status = str(payload.get("status") or payload.get("data_quality") or "").strip().lower() or None

    if block_reasons or catalyst_bias in BLOCKING_CATALYST_BIASES or event_risk in {"block", "blocked"}:
        return 0.0, _component_result(
            name="catalyst",
            score=0.0,
            available=True,
            confidence=max(confidence, 0.75),
            blocked=True,
            reason="catalyst_blocked",
            extras={"status": status, "catalyst_bias": catalyst_bias or None, "missing_numeric_score": False},
        )
    if catalyst_bias in NEGATIVE_CATALYST_BIASES:
        score = _clamp_score(35 - 20 * (1 - confidence), 25.0)
        return score, _component_result(
            name="catalyst",
            score=score,
            available=True,
            confidence=max(confidence, 0.5),
            reason="explicit_negative_catalyst",
            extras={"status": status, "catalyst_bias": catalyst_bias or None, "missing_numeric_score": False},
        )

    explicit_score = payload.get("catalyst_score")
    if explicit_score is None:
        explicit_score = payload.get("score")
    if explicit_score is not None:
        score = _clamp_score(explicit_score, 50.0)
        return score, _component_result(
            name="catalyst",
            score=score,
            available=True,
            confidence=confidence,
            reason="ok",
            extras={"status": status, "catalyst_bias": catalyst_bias or None, "missing_numeric_score": False},
        )

    if status == "completed":
        return 50.0, _component_result(
            name="catalyst",
            score=50.0,
            available=True,
            confidence=0.5,
            reason="completed_without_numeric_score",
            extras={"status": status, "catalyst_bias": catalyst_bias or None, "missing_numeric_score": True},
        )
    if status == "partial":
        return 50.0, _component_result(
            name="catalyst",
            score=50.0,
            available=True,
            confidence=0.25,
            reason="partial_without_numeric_score",
            extras={"status": status, "catalyst_bias": catalyst_bias or None, "missing_numeric_score": True},
        )

    if positive_catalysts and not negative_catalysts:
        score = _clamp_score(55 + 10 * confidence, 60.0)
        return score, _component_result(
            name="catalyst",
            score=score,
            available=True,
            confidence=confidence,
            reason="positive_catalyst_context",
            extras={"status": status, "catalyst_bias": catalyst_bias or None, "missing_numeric_score": True},
        )
    if negative_catalysts and not positive_catalysts:
        score = _clamp_score(45 - 10 * confidence, 40.0)
        return score, _component_result(
            name="catalyst",
            score=score,
            available=True,
            confidence=confidence,
            reason="negative_catalyst_context",
            extras={"status": status, "catalyst_bias": catalyst_bias or None, "missing_numeric_score": True},
        )
    return 50.0, _component_result(
        name="catalyst",
        score=50.0,
        available=False,
        confidence=0.0,
        reason="catalyst_unavailable",
        extras={"status": status, "catalyst_bias": catalyst_bias or None, "missing_numeric_score": True},
    )


def score_candidate(
    *,
    symbol: str,
    dsa: dict[str, Any],
    kronos: dict[str, Any],
    technical: dict[str, Any],
    quote: dict[str, Any],
    catalyst: dict[str, Any],
    min_effective_coverage: float = MIN_EFFECTIVE_COVERAGE,
) -> dict[str, Any]:
    normalized = symbol.upper()
    dsa_score, dsa_diagnostics, block_reasons = _dsa_diagnostic(normalized, dsa)
    overlap_flags = _dsa_overlap_flags(normalized, dsa)
    technical_score, technical_diagnostics = _technical_component(normalized, technical)
    kronos_score, kronos_diagnostics = _kronos_component(normalized, kronos)
    quote_score, quote_diagnostics = _quote_component(normalized, quote)
    catalyst_score, catalyst_diagnostics = _catalyst_component(normalized, catalyst)
    components = {
        "dsa": round(dsa_score, 2),
        "technical": round(technical_score, 2),
        "kronos": round(kronos_score, 2),
        "quote": round(quote_score, 2),
        "catalyst": round(catalyst_score, 2),
    }
    diagnostics = {
        "dsa": dsa_diagnostics,
        "technical": technical_diagnostics,
        "kronos": kronos_diagnostics,
        "quote": quote_diagnostics,
        "catalyst": catalyst_diagnostics,
    }
    effective_weight_total = round(sum(float(payload.get("effective_weight", 0.0) or 0.0) for payload in diagnostics.values()), 4)
    weighted_total = sum(float(payload.get("contribution", 0.0) or 0.0) for payload in diagnostics.values())
    score = round(weighted_total / effective_weight_total, 2) if effective_weight_total > 0 else 50.0
    coverage = round(effective_weight_total / sum(WEIGHTS.values()), 4) if WEIGHTS else 0.0
    missing_components = [name for name, payload in diagnostics.items() if not payload.get("available")]
    warnings: list[str] = []
    if coverage < min_effective_coverage:
        warnings.append("low_effective_coverage")
    for name, payload in diagnostics.items():
        if not payload.get("available"):
            warnings.append(f"missing_component:{name}")
        if payload.get("warning"):
            warnings.append(str(payload["warning"]))
    warnings = list(dict.fromkeys(warnings))
    blocked_reasons = list(block_reasons)
    component_block_reasons = [f"{name}:{payload.get('reason')}" for name, payload in diagnostics.items() if payload.get("blocked")]
    blocked_reasons.extend(component_block_reasons)
    blocked = bool(blocked_reasons)
    score_status = "blocked" if blocked else "insufficient_data" if coverage < min_effective_coverage else "scored"
    return {
        "symbol": normalized,
        "score": round(score, 2),
        "total_score": round(score, 2),
        "score_status": score_status,
        "coverage": coverage,
        "missing_components": missing_components,
        "components": components,
        "weights": dict(WEIGHTS),
        "diagnostics": diagnostics,
        "warnings": warnings,
        "blocked": blocked,
        "block_reasons": list(dict.fromkeys(blocked_reasons)),
        "overlap_flags": overlap_flags,
    }


def build_candidate_scores_from_paths(agent_root: Path, run_date: str) -> dict[str, Any]:
    paths = build_runtime_paths(agent_root, run_date=run_date)
    scoring_profile = load_scoring_profile(paths.config_dir)
    candidate_snapshot = _read_json_or_empty(paths.candidate_snapshot_path)
    quote_core = _read_json_or_empty(paths.quote_snapshot_core_path)
    quote_candidates = _read_json_or_empty(paths.quote_snapshot_candidates_path)
    quote = {"symbols": {**(quote_core.get("symbols") or {}), **(quote_candidates.get("symbols") or {})}}
    selected_symbols = [str(symbol).upper() for symbol in candidate_snapshot.get("selected_symbols", [])]
    dsa = _read_json_or_empty(paths.dsa_signals_path)
    kronos = _read_json_or_empty(paths.kronos_signals_path)
    technical = _read_json_or_empty(paths.technical_signals_path)
    catalyst = _read_json_or_empty(paths.catalyst_snapshot_path)
    min_coverage = float(scoring_profile.get("min_effective_coverage", MIN_EFFECTIVE_COVERAGE))

    symbols = {
        symbol: score_candidate(
            symbol=symbol,
            dsa=dsa,
            kronos=kronos,
            technical=technical,
            quote=quote,
            catalyst=catalyst,
            min_effective_coverage=min_coverage,
        )
        for symbol in selected_symbols
    }
    ranked = sorted(symbols, key=lambda item: (symbols[item]["blocked"], -float(symbols[item]["score"]), item))
    payload = {
        "date": run_date,
        "generated_at": datetime.now(tz=PT).isoformat(),
        "weights": dict(WEIGHTS),
        "scoring_profile": scoring_profile,
        "symbols": symbols,
        "ranked_symbols": ranked,
        "notes": "Deterministic aggregation of existing signal-layer outputs; does not create new AI reasoning.",
    }
    write_json(paths.candidate_scores_path, payload)
    return payload


# --- H4: challenger re-scoring (expensive-path shadow strategies) -----------------------------
# Re-aggregate a candidate's score under a challenger config WITHOUT re-running the analyzers,
# by reusing each component's already-persisted point-in-time raw score + confidence. Three levers:
#   1. disabled_components  — zero a component's weight (e.g. no_kronos_shadow: drop kronos)
#   2. component_weights    — override base weights (e.g. validate an E2 weight suggestion)
#   3. factor_alpha + factor_alpha_weight — fold the H2 factor_alpha layer in as an extra component
#      (baseline_v1_plus_price_factors_shadow), letting a challenger score WITH factors while the
#      champion stays write-only. All read-only over persisted artifacts → point-in-time safe.


def rescore_candidate(
    scored: dict[str, Any],
    *,
    component_weights: dict[str, float] | None = None,
    disabled_components: set[str] | None = None,
    factor_alpha_score: float | None = None,
    factor_alpha_weight: float = 0.0,
    min_effective_coverage: float = MIN_EFFECTIVE_COVERAGE,
) -> dict[str, Any]:
    """Pure: recompute one candidate's aggregate score under a challenger config.

    Reuses the persisted per-component `score`/`confidence`/`available` from the champion's
    diagnostics — equivalent in scoring effect to re-running with the component enabled/disabled
    or reweighted, but cheap and point-in-time safe. Returns a new scored dict (champion untouched).
    """
    weights_override = component_weights or {}
    disabled = {str(name) for name in (disabled_components or set())}
    diagnostics = dict(scored.get("diagnostics") or {})

    new_diagnostics: dict[str, Any] = {}
    components: dict[str, float] = {}
    base_weight_total = 0.0
    for name, payload in diagnostics.items():
        if not isinstance(payload, dict):
            continue
        raw_score = float(payload.get("score", 50.0) or 50.0)
        confidence = float(payload.get("confidence", 0.0) or 0.0)
        available = bool(payload.get("available"))
        if name in disabled:
            base_weight = 0.0
        else:
            base_weight = float(weights_override.get(name, WEIGHTS.get(name, 0.0)))
        base_weight_total += base_weight
        effective_weight = round(base_weight * confidence, 4) if available else 0.0
        contribution = round(raw_score * effective_weight, 2)
        updated = dict(payload)
        updated.update({
            "weight": base_weight,
            "component_weight": base_weight,
            "effective_weight": effective_weight,
            "contribution": contribution,
            "weighted_contribution": contribution,
        })
        new_diagnostics[name] = updated
        components[name] = round(raw_score, 2)

    # H4: fold in the H2 factor_alpha layer as an extra component if the challenger asks for it.
    if factor_alpha_score is not None and factor_alpha_weight > 0:
        fa_score = float(factor_alpha_score)
        effective_weight = round(factor_alpha_weight, 4)
        contribution = round(fa_score * effective_weight, 2)
        base_weight_total += factor_alpha_weight
        new_diagnostics["factor_alpha"] = {
            "score": round(fa_score, 2),
            "available": True,
            "confidence": 1.0,
            "blocked": False,
            "reason": "factor_alpha_layer",
            "weight": factor_alpha_weight,
            "component_weight": factor_alpha_weight,
            "effective_weight": effective_weight,
            "contribution": contribution,
            "weighted_contribution": contribution,
        }
        components["factor_alpha"] = round(fa_score, 2)

    effective_weight_total = round(
        sum(float(p.get("effective_weight", 0.0) or 0.0) for p in new_diagnostics.values()), 4
    )
    weighted_total = sum(float(p.get("contribution", 0.0) or 0.0) for p in new_diagnostics.values())
    score = round(weighted_total / effective_weight_total, 2) if effective_weight_total > 0 else 50.0
    coverage = round(effective_weight_total / base_weight_total, 4) if base_weight_total > 0 else 0.0

    # block reasons carry over from the champion scoring (DSA promote/demote etc.), minus disabled comps
    block_reasons = [
        reason for reason in (scored.get("block_reasons") or [])
        if not any(reason.startswith(f"{d}:") for d in disabled)
    ]
    component_block_reasons = [
        f"{name}:{p.get('reason')}" for name, p in new_diagnostics.items() if p.get("blocked")
    ]
    for reason in component_block_reasons:
        if reason not in block_reasons:
            block_reasons.append(reason)
    blocked = bool(block_reasons)
    score_status = "blocked" if blocked else "insufficient_data" if coverage < min_effective_coverage else "scored"

    result = dict(scored)
    result.update({
        "score": score,
        "total_score": score,
        "score_status": score_status,
        "coverage": coverage,
        "components": components,
        "diagnostics": new_diagnostics,
        "blocked": blocked,
        "block_reasons": list(dict.fromkeys(block_reasons)),
    })
    return result


def rescore_candidate_scores(
    champion_scores: dict[str, Any],
    *,
    component_weights: dict[str, float] | None = None,
    disabled_components: set[str] | None = None,
    factor_alpha: dict[str, Any] | None = None,
    factor_alpha_weight: float = 0.0,
    min_effective_coverage: float = MIN_EFFECTIVE_COVERAGE,
) -> dict[str, Any]:
    """Pure: re-aggregate every candidate's score under a challenger config (H4 expensive path).

    `factor_alpha` is the persisted factor_alpha.json payload ({symbols: {SYM: {factor_alpha_score}}});
    its per-symbol score is folded in when factor_alpha_weight > 0. Returns a candidate_scores-shaped
    dict the challenger risk overlay can consume directly. Champion scores are never mutated.
    """
    fa_symbols = (factor_alpha or {}).get("symbols") or {}
    champ_symbols = champion_scores.get("symbols") or {}
    rescored: dict[str, Any] = {}
    for symbol, scored in champ_symbols.items():
        if not isinstance(scored, dict):
            continue
        fa_payload = fa_symbols.get(symbol) or fa_symbols.get(str(symbol).upper()) or {}
        fa_score = fa_payload.get("factor_alpha_score") if isinstance(fa_payload, dict) else None
        rescored[symbol] = rescore_candidate(
            scored,
            component_weights=component_weights,
            disabled_components=disabled_components,
            factor_alpha_score=fa_score,
            factor_alpha_weight=factor_alpha_weight,
            min_effective_coverage=min_effective_coverage,
        )
    ranked = sorted(rescored, key=lambda item: (rescored[item]["blocked"], -float(rescored[item]["score"]), item))
    result = dict(champion_scores)
    result["symbols"] = rescored
    result["ranked_symbols"] = ranked
    result["rescored"] = True
    return result
