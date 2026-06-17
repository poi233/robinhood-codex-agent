from __future__ import annotations

import re
from typing import Any

# Canonical AI-signal envelope (H3 step 1). Every AI layer (Kronos / DSA / Catalyst) is normalized
# into this one shape so calibration, the AI-signal study, and ablation can treat them uniformly and
# attribute forward returns by layer. The fields are deliberately the ChatGPT-Phase-3 contract:
# asof_date (point-in-time, anti-cheat), direction, confidence, reason_codes, warning_codes,
# time_horizon, risk_flags. The normalizers DERIVE these from each layer's existing output, so no LLM
# prompt contract changes and nothing on the hot path moves — the layer is write-only advisory.

DIRECTIONS = ("long", "short", "neutral")
TIME_HORIZONS = ("intraday", "multi_day", "swing", "event", "unknown")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Categorical confidence words (DSA emits high/medium/low) mapped to a float midpoint.
_CONFIDENCE_WORDS = {"high": 0.8, "medium": 0.55, "med": 0.55, "low": 0.3, "none": 0.1}
# Catalyst data-quality used as a confidence proxy (the layer has no native confidence).
_DATA_QUALITY_CONFIDENCE = {"ok": 0.6, "partial": 0.3, "failed": 0.1}


def _coerce_confidence(value: Any) -> float:
    """Normalize a numeric or categorical confidence into a float in [0, 1]. Uncoercible -> 0.0."""
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    if isinstance(value, str):
        word = value.strip().lower()
        if word in _CONFIDENCE_WORDS:
            return _CONFIDENCE_WORDS[word]
        try:
            return max(0.0, min(1.0, float(word)))
        except ValueError:
            return 0.0
    return 0.0


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, (str, int, float)) and str(item).strip()]


def make_envelope(
    *,
    layer: str,
    symbol: str,
    asof_date: str,
    direction: str,
    confidence: float,
    time_horizon: str,
    reason_codes: list[str],
    warning_codes: list[str],
    risk_flags: list[str],
    raw_confidence: Any = None,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "layer": layer,
        "symbol": symbol.upper(),
        "asof_date": asof_date,
        "direction": direction,
        "confidence": round(float(confidence), 4),
        "time_horizon": time_horizon,
        "reason_codes": reason_codes,
        "warning_codes": warning_codes,
        "risk_flags": risk_flags,
        "raw_confidence": raw_confidence,
        "metrics": metrics or {},
    }


def validate_ai_signal(env: dict[str, Any]) -> list[str]:
    """Return a list of contract violations (empty == valid). Enforces the anti-cheat keystone
    (asof_date present + ISO date) plus type/range checks on every standardized field."""
    errors: list[str] = []
    if not env.get("layer"):
        errors.append("missing_layer")
    if not env.get("symbol"):
        errors.append("missing_symbol")
    asof = env.get("asof_date")
    if not isinstance(asof, str) or not _DATE_RE.match(asof):
        errors.append("missing_or_invalid_asof_date")
    if env.get("direction") not in DIRECTIONS:
        errors.append("invalid_direction")
    confidence = env.get("confidence")
    if not isinstance(confidence, (int, float)) or not (0.0 <= float(confidence) <= 1.0):
        errors.append("invalid_confidence")
    if env.get("time_horizon") not in TIME_HORIZONS:
        errors.append("invalid_time_horizon")
    for field in ("reason_codes", "warning_codes", "risk_flags"):
        value = env.get(field)
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            errors.append(f"invalid_{field}")
    return errors


# ---- Per-layer normalizers --------------------------------------------------------------------

_KRONOS_DIRECTION = {"bullish": "long", "bearish": "short", "neutral": "neutral"}


def normalize_kronos_signal(symbol: str, signal: dict[str, Any], *, asof_date: str, time_horizon: str = "intraday") -> dict[str, Any]:
    bias = str(signal.get("direction_bias") or "neutral").lower()
    setup = str(signal.get("setup_bias") or "").strip()
    path = str(signal.get("path_summary") or "").strip()
    reason_codes = [c for c in (f"setup:{setup}" if setup else "", f"path:{path}" if path else "") if c]
    return make_envelope(
        layer="kronos",
        symbol=symbol,
        asof_date=asof_date,
        direction=_KRONOS_DIRECTION.get(bias, "neutral"),
        confidence=_coerce_confidence(signal.get("confidence")),
        time_horizon=time_horizon,
        reason_codes=reason_codes,
        warning_codes=[],
        risk_flags=_str_list(signal.get("risk_flags")),
        raw_confidence=signal.get("confidence"),
        metrics={
            "predicted_return_bps": signal.get("predicted_return_bps"),
            "predicted_volatility_bps": signal.get("predicted_volatility_bps"),
        },
    )


def _dsa_direction(signal: dict[str, Any]) -> str:
    use = str(signal.get("suggested_premarket_use") or "").lower()
    if use == "promote":
        return "long"
    if use in {"demote", "block"}:
        return "neutral"  # DSA is a long-bias theme/gate layer; demote/block is "stand aside", not short
    bias = str(signal.get("bias") or "").lower()
    if bias in {"strong_candidate", "candidate"}:
        return "long"
    return "neutral"


def normalize_dsa_signal(symbol: str, signal: dict[str, Any], *, asof_date: str) -> dict[str, Any]:
    reason_codes = _str_list(signal.get("strategy_matches"))
    setup = str(signal.get("setup") or "").strip()
    if setup:
        reason_codes = [*reason_codes, f"setup:{setup}"]
    warning_codes = _str_list(signal.get("reject_reasons"))
    for field in ("crowding_risk", "macro_sensitivity"):
        if str(signal.get(field) or "").lower() == "high":
            warning_codes = [*warning_codes, f"{field}:high"]
    return make_envelope(
        layer="dsa",
        symbol=symbol,
        asof_date=asof_date,
        direction=_dsa_direction(signal),
        confidence=_coerce_confidence(signal.get("confidence")),
        time_horizon="multi_day",
        reason_codes=reason_codes,
        warning_codes=warning_codes,
        risk_flags=_str_list(signal.get("risk_flags")),
        raw_confidence=signal.get("confidence"),
        metrics={"dsa_score": signal.get("dsa_score"), "theme_score": signal.get("theme_score")},
    )


def normalize_catalyst_signal(symbol: str, signal: dict[str, Any], *, asof_date: str) -> dict[str, Any]:
    catalysts = _str_list(signal.get("catalysts"))
    reason_codes = ["has_catalyst"] if catalysts else []
    earnings_risk = str(signal.get("earnings_risk") or "").lower()
    warning_codes: list[str] = []
    if earnings_risk == "near":
        warning_codes.append("earnings_risk_near")
    elif earnings_risk == "unknown":
        warning_codes.append("earnings_risk_unknown")
    data_quality = str(signal.get("data_quality") or "").lower()
    return make_envelope(
        layer="catalyst",
        symbol=symbol,
        asof_date=asof_date,
        direction="neutral",  # catalyst is risk/context, not a directional call
        confidence=_DATA_QUALITY_CONFIDENCE.get(data_quality, 0.1),
        time_horizon="event",
        reason_codes=reason_codes,
        warning_codes=warning_codes,
        risk_flags=_str_list(signal.get("risk_flags")),
        raw_confidence=data_quality or None,
        metrics={"catalyst_count": len(catalysts)},
    )
