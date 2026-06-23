"""Deterministic technical-signals engine.

Builds the decision-critical half of ``technical_signals.json`` from the
already-computed ``technical_features`` (SMA/EMA/RSI/MACD/ATR, swing points,
20-day range, multi-timeframe alignment, relative strength). Every field that
downstream scoring (``planner/scoring.py``), candidate selection
(``planner/candidates.py``) and the price-policy gate (via
``reporting/trader_watch_levels.py``) actually reads is produced here with exact,
reproducible rules — no LLM in the decision path.

The narrative-only fields (``chan``, ``brooks``, ``fundamentals``,
``decision_rationale``) are seeded with deterministic summaries and may be
enriched afterwards by an optional, advisory LLM pass. Nothing in the decision
path depends on that enrichment.

Schema matches ``signals/technical_fallback.build_failed_technical_payload`` so
the two are interchangeable for consumers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# Composite-score thresholds → (action, priority_score). Kept interpretable;
# priority_score is read directly by planner/scoring when present.
_ACTION_BANDS: list[tuple[float, str, float]] = [
    (6.0, "strong_promote", 88.0),
    (4.0, "promote", 80.0),
    (2.0, "buy_bias", 72.0),
    (-1.0, "observe", 50.0),
    (-3.0, "reduce", 32.0),
]
_AVOID = ("avoid", 8.0)

_BULLISH_ACTIONS = {"strong_promote", "promote", "buy_bias"}


def _f(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _atr_fallback(price: float, range_low: float, range_high: float) -> float:
    span = range_high - range_low
    if span > 0:
        return round(span * 0.1, 4)
    return round(max(price * 0.02, 0.01), 4)


def _nearest_below(price: float, levels: list[float]) -> list[float]:
    return sorted((lv for lv in levels if lv is not None and lv < price), reverse=True)


def _nearest_above(price: float, levels: list[float]) -> list[float]:
    return sorted(lv for lv in levels if lv is not None and lv > price)


def _composite_score(daily: dict[str, Any], alignment: str, rel_strength: dict[str, Any]) -> tuple[float, list[str]]:
    """Transparent bullishness score in roughly [-10, +10] with a reason trail."""
    score = 0.0
    reasons: list[str] = []

    trend = str(daily.get("trend") or "sideways")
    if trend == "up":
        score += 2.0
    elif trend == "down":
        score -= 2.0
    reasons.append(f"trend={trend}")

    if alignment == "bullish":
        score += 2.0
    elif alignment == "bearish":
        score -= 2.0
    reasons.append(f"align={alignment}")

    price_vs_sma = daily.get("price_vs_sma") or {}
    if price_vs_sma.get("200") == "above":
        score += 1.0
    elif price_vs_sma.get("200") == "below":
        score -= 1.0
    if price_vs_sma.get("50") == "above":
        score += 1.0
    elif price_vs_sma.get("50") == "below":
        score -= 1.0

    macd = daily.get("macd") or {}
    hist = _f(macd.get("hist"))
    if hist is not None:
        score += 1.0 if hist > 0 else -1.0
        reasons.append(f"macd_hist={'+' if hist > 0 else '-'}")

    rsi = _f(daily.get("rsi_14"))
    if rsi is not None:
        if 50.0 <= rsi <= 70.0:
            score += 1.0
        elif rsi < 40.0:
            score -= 1.0
        reasons.append(f"rsi={round(rsi, 1)}")

    rs20 = _f(rel_strength.get("20d"))
    if rs20 is not None:
        score += 1.0 if rs20 > 0 else -1.0
        reasons.append(f"relS20={round(rs20, 1)}")

    flags = daily.get("flags") or []
    if "range_breakout" in flags:
        score += 1.0
    if "pullback_to_sma20" in flags and trend == "up":
        score += 1.0
    if "gap_down" in flags:
        score -= 1.0

    return score, reasons


def _is_chasing(daily: dict[str, Any]) -> bool:
    rsi = _f(daily.get("rsi_14"))
    dist = _f(daily.get("dist_from_recent_high_pct"))
    surge = _f(daily.get("volume_surge_ratio"))
    if rsi is not None and rsi >= 78.0:
        return True
    if dist is not None and dist <= 0.5 and surge is not None and surge >= 2.0:
        return True
    return False


def _action_for_score(score: float) -> tuple[str, float]:
    for threshold, action, priority in _ACTION_BANDS:
        if score >= threshold:
            return action, priority
    return _AVOID


def _confidence(score: float, alignment: str, action: str, data_quality: str) -> float:
    conf = 0.3 + 0.07 * min(abs(score), 8.0)
    if (alignment == "bullish" and action in _BULLISH_ACTIONS) or (
        alignment == "bearish" and action in {"reduce", "avoid"}
    ):
        conf += 0.1
    if data_quality == "partial":
        conf -= 0.1
    return round(max(0.0, min(conf, 0.95)), 2)


def _build_levels(daily: dict[str, Any]) -> dict[str, Any]:
    price = _f(daily.get("last_close")) or 0.0
    range_20d = daily.get("range_20d") or {}
    range_high = _f(range_20d.get("high")) or _f(daily.get("high_recent")) or price * 1.05
    range_low = _f(range_20d.get("low")) or _f(daily.get("low_recent")) or price * 0.95

    swing_highs = [_f(v) for v in (daily.get("swing_highs") or [])]
    swing_lows = [_f(v) for v in (daily.get("swing_lows") or [])]
    sma20 = _f((daily.get("sma") or {}).get("20"))

    resistance_levels = _nearest_above(price, [*swing_highs, range_high, _f(daily.get("high_recent"))])
    support_levels = _nearest_below(price, [*swing_lows, range_low, sma20, _f(daily.get("low_recent"))])

    resistance_1 = resistance_levels[0] if resistance_levels else round(price * 1.03, 4)
    resistance_2 = resistance_levels[1] if len(resistance_levels) > 1 else round(max(resistance_1, range_high), 4)
    support_1 = support_levels[0] if support_levels else round(price * 0.97, 4)
    support_2 = support_levels[1] if len(support_levels) > 1 else round(min(support_1, range_low), 4)

    return {
        "price": round(price, 4),
        "range_low": round(range_low, 4),
        "range_high": round(range_high, 4),
        "support_1": round(support_1, 4),
        "support_2": round(support_2, 4),
        "resistance_1": round(resistance_1, 4),
        "resistance_2": round(resistance_2, 4),
        "sma20": round(sma20, 4) if sma20 is not None else None,
        "supports": sorted({round(support_1, 4), round(support_2, 4)}),
        "resistances": sorted({round(resistance_1, 4), round(resistance_2, 4)}),
    }


def _build_setups(
    daily: dict[str, Any],
    levels: dict[str, Any],
    action: str,
    atr: float,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    price = levels["price"]
    support_1 = levels["support_1"]
    support_2 = levels["support_2"]
    resistance_1 = levels["resistance_1"]
    resistance_2 = levels["resistance_2"]
    range_high = levels["range_high"]
    range_low = levels["range_low"]
    sma20 = levels["sma20"]
    flags = daily.get("flags") or []
    trend = str(daily.get("trend") or "sideways")
    bullish = action in _BULLISH_ACTIONS

    breakout = "range_breakout" in flags or price >= resistance_1 * 0.999
    near_support = sma20 is not None and abs(price - support_1) / max(price, 1e-9) <= 0.02
    pullback = trend == "up" and (("pullback_to_sma20" in flags) or near_support)

    if bullish and breakout:
        setup_type = "breakout"
        trigger_above = round(resistance_1, 4)
        entry_low, entry_high = round(resistance_1, 4), round(resistance_1 + 0.3 * atr, 4)
        do_not_chase_above = round(resistance_1 + 1.5 * atr, 4)
        status = "valid"
    elif bullish and pullback:
        setup_type = "pullback"
        trigger_above = round(resistance_1, 4)
        entry_low, entry_high = round(support_1, 4), round(support_1 + 0.5 * atr, 4)
        do_not_chase_above = round(resistance_1 + 0.5 * atr, 4)
        status = "valid"
    else:
        setup_type = "none"
        trigger_above = round(resistance_1, 4)
        entry_low = entry_high = round(price, 4)
        do_not_chase_above = round(resistance_1, 4)
        status = "watch" if trend == "up" else "invalid"

    invalidation_below = round(support_1 - 0.2 * atr, 4)
    target_1 = round(max(price + atr, resistance_1), 4)
    target_2 = round(max(price + 2.0 * atr, resistance_2, range_high), 4)

    long_setup = {
        "status": status,
        "setup_type": setup_type,
        "trigger_above": trigger_above,
        "entry_zone": {"low": entry_low, "high": entry_high},
        "invalidation_below": invalidation_below,
        "target_1": target_1,
        "target_2": target_2,
        "do_not_chase_above": do_not_chase_above,
        "notes": f"engine deterministic setup ({setup_type})",
    }

    short_setup = {
        # "watch" (not "valid"): policy/sell.evaluate_sell only arms the risk_exit
        # path when short_setup.status is in {"active", "watch"}. The risk-reduction
        # setup is always standing, so it is a "watch".
        "status": "watch",
        "setup_type": "risk_reduction",
        "trigger_below": round(support_1, 4),
        "entry_zone": {"low": round(support_1, 4), "high": round(support_1, 4)},
        "invalidation_above": round(resistance_1, 4),
        "target_1": round(min(support_2, price - atr), 4),
        "target_2": round(range_low, 4),
        "do_not_chase_below": round(range_low, 4),
        "notes": "Risk-reduction only for existing longs; never permission to open a short.",
    }
    return long_setup, short_setup, setup_type


def _phase(trend: str, alignment: str) -> str:
    if trend == "up":
        return "markup" if alignment == "bullish" else "uptrend_pullback"
    if trend == "down":
        return "markdown" if alignment == "bearish" else "downtrend_bounce"
    return "range"


def _alignment_label(alignment: str) -> str:
    return {"bullish": "aligned_bull", "bearish": "aligned_bear"}.get(alignment, "conflicted")


def _build_symbol(symbol: str, features: dict[str, Any]) -> dict[str, Any]:
    timeframes = features.get("timeframes") or {}
    daily = timeframes.get("daily")
    data_quality = str(features.get("data_quality") or "ok")
    multi = features.get("multi_timeframe") or {}
    alignment = str(multi.get("alignment") or "mixed")
    rel_strength = multi.get("rel_strength_vs_spy") or {}

    if not isinstance(daily, dict) or data_quality == "failed" or _f(daily.get("last_close")) is None:
        return _avoid_symbol("no usable daily timeframe data; technical engine fail-closed")

    score, reasons = _composite_score(daily, alignment, rel_strength)
    action, priority = _action_for_score(score)

    chasing = _is_chasing(daily)
    if chasing and action in _BULLISH_ACTIONS:
        action, priority = "observe", 50.0
        reasons.append("chase_guard")

    levels = _build_levels(daily)
    price = levels["price"]
    atr = _f(daily.get("atr_14")) or _atr_fallback(price, levels["range_low"], levels["range_high"])
    long_setup, short_setup, setup_type = _build_setups(daily, levels, action, atr)
    trend = str(daily.get("trend") or "sideways")

    if action in _BULLISH_ACTIONS:
        no_trade_zone = {"low": 0.0, "high": 0.0, "reason": "active long setup; trade the entry/trigger levels"}
    else:
        no_trade_zone = {
            "low": round(levels["support_1"], 4),
            "high": round(levels["resistance_1"], 4),
            "reason": f"no edge ({action}); chop between nearest support and resistance",
        }

    confidence = _confidence(score, alignment, action, data_quality)
    rationale = f"engine: {', '.join(reasons)}, score={round(score, 1)} -> {action} (setup={setup_type})"

    return {
        "technical_phase": _phase(trend, alignment),
        "technical_action": action,
        "priority_score": round(priority, 2),
        "timeframe_stack": {"higher": "1w", "execution": "1d", "lower": "1h"},
        "timeframe_alignment": _alignment_label(alignment),
        "key_levels": {
            "reference_price": price,
            "supports": levels["supports"],
            "resistances": levels["resistances"],
            "range_low": levels["range_low"],
            "range_high": levels["range_high"],
        },
        "long_setup": long_setup,
        "short_setup": short_setup,
        "no_trade_zone": no_trade_zone,
        "chan": {
            "signal": "none",
            "state": "engine_deterministic",
            "invalidation": f"below {long_setup['invalidation_below']}",
            "next_confirmation": "pending optional narrative enrichment",
        },
        "brooks": {
            "setup": setup_type,
            "entry_style": "stop" if setup_type == "breakout" else "limit" if setup_type == "pullback" else "none",
            "target_logic": "measured-move / next resistance",
            "downgrade_condition": "pending optional narrative enrichment",
        },
        "fundamentals": {
            "event_bias": "neutral",
            "event_type": "none",
            "quality_flag": "watch",
        },
        "decision_rationale": rationale,
        "confidence": confidence,
        "engine": {
            "source": "technical_engine",
            "score": round(score, 2),
            "atr_14": round(atr, 4),
            "data_quality": data_quality,
        },
    }


def _avoid_symbol(reason: str) -> dict[str, Any]:
    return {
        "technical_phase": "unclear",
        "technical_action": "avoid",
        "priority_score": 0.0,
        "timeframe_stack": {"higher": "1w", "execution": "1d", "lower": "1h"},
        "timeframe_alignment": "conflicted",
        "key_levels": {
            "reference_price": 0.0,
            "supports": [0.0],
            "resistances": [999999.0],
            "range_low": 0.0,
            "range_high": 999999.0,
        },
        "long_setup": {
            "status": "invalid",
            "setup_type": "none",
            "trigger_above": 999999.0,
            "entry_zone": {"low": 0.0, "high": 0.0},
            "invalidation_below": 0.0,
            "target_1": 999999.0,
            "target_2": 999999.0,
            "do_not_chase_above": 999999.0,
            "notes": reason,
        },
        "short_setup": {
            "status": "invalid",
            "setup_type": "none",
            "trigger_below": 0.0,
            "entry_zone": {"low": 0.0, "high": 0.0},
            "invalidation_above": 999999.0,
            "target_1": 0.0,
            "target_2": 0.0,
            "do_not_chase_below": 0.0,
            "notes": "Risk-reduction only for existing longs; never permission to open a short.",
        },
        "no_trade_zone": {"low": 0.0, "high": 999999.0, "reason": reason},
        "chan": {"signal": "none", "state": "no_data", "invalidation": reason, "next_confirmation": reason},
        "brooks": {"setup": "none", "entry_style": "none", "target_logic": "none", "downgrade_condition": reason},
        "fundamentals": {"event_bias": "neutral", "event_type": "none", "quality_flag": "watch"},
        "decision_rationale": reason,
        "confidence": 0.0,
        "engine": {"source": "technical_engine", "score": 0.0, "atr_14": 0.0, "data_quality": "failed"},
    }


def build_technical_signals(
    features_payload: dict[str, Any],
    *,
    run_date: str,
    source_feed_manifest: str = "",
) -> dict[str, Any]:
    """Build a full technical_signals payload deterministically from features.

    ``features_payload`` is the output of
    ``planner.technical_features.build_technical_features``.
    """
    symbols_features = features_payload.get("symbols") or {}
    symbols: dict[str, Any] = {}
    for symbol, feats in symbols_features.items():
        if not isinstance(symbol, str) or not isinstance(feats, dict):
            continue
        symbols[symbol] = _build_symbol(symbol, feats)

    return {
        "date": run_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_feed_manifest": source_feed_manifest,
        "analysis_status": "engine" if symbols else "empty",
        "symbols": symbols,
        "notes": "decision-critical technical signals computed deterministically by technical_engine",
    }
