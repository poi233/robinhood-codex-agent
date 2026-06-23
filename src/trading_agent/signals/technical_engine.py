"""Technical-signals engine (deterministic core + bounded LLM reconciliation).

Stage 1 — deterministic engine (``build_technical_signals``): builds every
decision-critical field of ``technical_signals.json`` from the precomputed
``technical_features``. It now uses *all* of the computed inputs:

- every timeframe (weekly / daily / hourly / intraday_15m), weighted, not just a
  single alignment label;
- EMA 9/21, SMA 20/50/200, MACD histogram, RSI per timeframe;
- multi-horizon relative strength (5d / 20d / 60d);
- ATR (levels + ``atr_pct`` volatility context) and average volume (liquidity);
- price-action flags (breakout / pullback / gaps / inside bar).

Stage 2 — bounded LLM reconciliation (``apply_llm_assessment``): the advisory
narrative prompt also emits a structured ``llm_assessment`` per symbol. This
function folds that opinion into the decision **within hard bounds** — it can
swing ``priority_score`` by at most ``TECHNICAL_LLM_MAX_SWING`` points and may
``veto`` (caution-only downgrade). It never touches the deterministic price
levels / stops / no-trade zone, so the price-policy gate's risk controls always
stand even if the model is wrong.

Schema matches ``signals/technical_fallback.build_failed_technical_payload`` so
consumers are unchanged.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

# Per-timeframe weights for the composite directional score. Missing timeframes
# are dropped and the remaining weights re-normalized, so a partial feed never
# silently biases the score.
_TF_WEIGHTS: dict[str, float] = {
    "weekly": 0.30,
    "daily": 0.40,
    "hourly": 0.20,
    "intraday_15m": 0.10,
}

# priority_score floor per action (single source of truth shared by the engine
# and the reconciler). priority_score is read directly by planner/scoring.
_ACTION_FLOORS: list[tuple[float, str]] = [
    (84.0, "strong_promote"),
    (76.0, "promote"),
    (66.0, "buy_bias"),
    (45.0, "observe"),
    (30.0, "reduce"),
]
_AVOID_ACTION = "avoid"
_ACTION_ORDER = ["avoid", "reduce", "observe", "buy_bias", "promote", "strong_promote"]
_BULLISH_ACTIONS = {"strong_promote", "promote", "buy_bias"}

_BIAS_MAP = {
    "bullish": 1.0,
    "positive": 1.0,
    "long": 1.0,
    "buy": 1.0,
    "neutral": 0.0,
    "none": 0.0,
    "": 0.0,
    "bearish": -1.0,
    "negative": -1.0,
    "short": -1.0,
    "sell": -1.0,
    "avoid": -1.0,
    "reduce": -1.0,
}


def _f(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _sign(value: float) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


def _action_from_priority(priority: float) -> str:
    for floor, action in _ACTION_FLOORS:
        if priority >= floor:
            return action
    return _AVOID_ACTION


def _atr_fallback(price: float, range_low: float, range_high: float) -> float:
    span = range_high - range_low
    if span > 0:
        return round(span * 0.1, 4)
    return round(max(price * 0.02, 0.01), 4)


def _nearest_below(price: float, levels: list[float | None]) -> list[float]:
    return sorted((lv for lv in levels if lv is not None and lv < price), reverse=True)


def _nearest_above(price: float, levels: list[float | None]) -> list[float]:
    return sorted(lv for lv in levels if lv is not None and lv > price)


# --------------------------------------------------------------------------- #
# Stage 1 — deterministic multi-timeframe scoring
# --------------------------------------------------------------------------- #
def _tf_directional(tf: dict[str, Any] | None) -> float | None:
    """Directional bullishness of a single timeframe in [-1, 1].

    Combines trend, price-vs-SMA(20/50/200), EMA 9/21 cross, MACD histogram and
    RSI. Returns None when the timeframe is absent.
    """
    if not isinstance(tf, dict) or not tf:
        return None
    s = 0.0
    trend = str(tf.get("trend") or "sideways")
    if trend == "up":
        s += 0.40
    elif trend == "down":
        s -= 0.40

    pvs = tf.get("price_vs_sma") or {}
    for period, weight in (("200", 0.15), ("50", 0.12), ("20", 0.08)):
        if pvs.get(period) == "above":
            s += weight
        elif pvs.get(period) == "below":
            s -= weight

    ema = tf.get("ema") or {}
    e9, e21 = _f(ema.get("9")), _f(ema.get("21"))
    if e9 is not None and e21 is not None:
        s += 0.10 if e9 >= e21 else -0.10

    hist = _f((tf.get("macd") or {}).get("hist"))
    if hist is not None:
        s += 0.08 if hist > 0 else -0.08

    rsi = _f(tf.get("rsi_14"))
    if rsi is not None:
        if 50.0 <= rsi <= 70.0:
            s += 0.07
        elif rsi > 78.0:
            s -= 0.05
        elif rsi < 40.0:
            s -= 0.07

    return _clamp(s, -1.0, 1.0)


def _multi_tf_directional(timeframes: dict[str, Any]) -> tuple[float | None, dict[str, float]]:
    total = 0.0
    wsum = 0.0
    per_tf: dict[str, float] = {}
    for label, weight in _TF_WEIGHTS.items():
        d = _tf_directional(timeframes.get(label))
        if d is None:
            continue
        per_tf[label] = round(d, 3)
        total += d * weight
        wsum += weight
    if wsum == 0.0:
        return None, {}
    return total / wsum, per_tf


def _rel_strength_dir(rel_strength: dict[str, Any]) -> float | None:
    values = [_f(rel_strength.get(k)) for k in ("5d", "20d", "60d")]
    present = [v for v in values if v is not None]
    if not present:
        return None
    return sum(1.0 if v > 0 else -1.0 if v < 0 else 0.0 for v in present) / len(present)


def _flag_adjustment(daily: dict[str, Any]) -> tuple[float, list[str]]:
    flags = daily.get("flags") or []
    trend = str(daily.get("trend") or "sideways")
    adj = 0.0
    hit: list[str] = []
    if "range_breakout" in flags:
        adj += 0.10
        hit.append("breakout")
    if "pullback_to_sma20" in flags and trend == "up":
        adj += 0.06
        hit.append("pullback")
    if "gap_up" in flags:
        adj += 0.04
        hit.append("gap_up")
    if "inside_bar" in flags and trend == "up":
        adj += 0.03
        hit.append("inside_bar")
    if "gap_down" in flags:
        adj -= 0.10
        hit.append("gap_down")
    return adj, hit


def _composite_direction(
    daily: dict[str, Any],
    timeframes: dict[str, Any],
    rel_strength: dict[str, Any],
) -> tuple[float, dict[str, Any]]:
    """Final directional score in [-1, 1] plus an audit breakdown."""
    mtf, per_tf = _multi_tf_directional(timeframes)
    if mtf is None:
        mtf, per_tf = _tf_directional(daily) or 0.0, {"daily": round(_tf_directional(daily) or 0.0, 3)}

    rs_dir = _rel_strength_dir(rel_strength)
    flag_adj, flag_hits = _flag_adjustment(daily)

    # timeframe agreement: do the available timeframes point the same way?
    signs = [_sign(v) for v in per_tf.values() if v != 0]
    agreement = (sum(1 for s in signs if s == _sign(mtf)) / len(signs)) if signs else 0.5
    align_bonus = 0.05 if agreement >= 0.99 else (-0.05 if agreement <= 0.34 else 0.0)

    direction = 0.75 * mtf + 0.15 * (rs_dir or 0.0) + flag_adj + align_bonus
    direction = _clamp(direction, -1.0, 1.0)

    breakdown = {
        "per_timeframe": per_tf,
        "multi_tf": round(mtf, 3),
        "rel_strength_dir": round(rs_dir, 3) if rs_dir is not None else None,
        "flag_adjustment": round(flag_adj, 3),
        "flags": flag_hits,
        "timeframe_agreement": round(agreement, 3),
        "alignment_bonus": align_bonus,
        "direction": round(direction, 3),
    }
    return direction, breakdown


def _is_chasing(daily: dict[str, Any]) -> bool:
    rsi = _f(daily.get("rsi_14"))
    dist = _f(daily.get("dist_from_recent_high_pct"))
    surge = _f(daily.get("volume_surge_ratio"))
    if rsi is not None and rsi >= 78.0:
        return True
    if dist is not None and dist <= 0.5 and surge is not None and surge >= 2.0:
        return True
    return False


def _confidence(
    direction: float,
    agreement: float,
    data_quality: str,
    atr_pct: float | None,
    avg_volume_20: float | None,
) -> float:
    conf = 0.35 + 0.45 * abs(direction)
    conf += 0.10 * (agreement - 0.5) * 2.0  # ±0.10 by timeframe agreement
    if atr_pct is not None and atr_pct > 8.0:  # very high volatility → less trustworthy
        conf -= 0.10
    if data_quality == "partial":
        conf -= 0.10
    if avg_volume_20 is None:  # liquidity unknown
        conf -= 0.05
    return round(_clamp(conf, 0.0, 0.95), 2)


def _build_levels(daily: dict[str, Any]) -> dict[str, Any]:
    price = _f(daily.get("last_close")) or 0.0
    range_20d = daily.get("range_20d") or {}
    range_high = _f(range_20d.get("high")) or _f(daily.get("high_recent")) or price * 1.05
    range_low = _f(range_20d.get("low")) or _f(daily.get("low_recent")) or price * 0.95

    swing_highs = [_f(v) for v in (daily.get("swing_highs") or [])]
    swing_lows = [_f(v) for v in (daily.get("swing_lows") or [])]
    sma = daily.get("sma") or {}
    ema = daily.get("ema") or {}
    sma20 = _f(sma.get("20"))
    ema21 = _f(ema.get("21"))
    ema9 = _f(ema.get("9"))

    resistance_levels = _nearest_above(
        price, [*swing_highs, range_high, _f(daily.get("high_recent")), ema9, ema21]
    )
    support_levels = _nearest_below(
        price, [*swing_lows, range_low, sma20, ema21, ema9, _f(daily.get("low_recent"))]
    )

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
        "ema21": round(ema21, 4) if ema21 is not None else None,
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
    ema21 = levels["ema21"]
    flags = daily.get("flags") or []
    trend = str(daily.get("trend") or "sideways")
    bullish = action in _BULLISH_ACTIONS

    # Prefer the dynamic moving-average support (ema21/sma20) as the pullback
    # anchor when price is sitting on it.
    pullback_anchor = support_1
    for ma in (ema21, sma20):
        if ma is not None and ma < price and abs(price - ma) / max(price, 1e-9) <= 0.03:
            pullback_anchor = max(pullback_anchor, ma)

    breakout = "range_breakout" in flags or price >= resistance_1 * 0.999
    near_support = abs(price - pullback_anchor) / max(price, 1e-9) <= 0.025
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
        entry_low, entry_high = round(pullback_anchor, 4), round(pullback_anchor + 0.5 * atr, 4)
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


def _phase(trend: str, direction: float) -> str:
    if trend == "up":
        return "markup" if direction >= 0.3 else "uptrend_pullback"
    if trend == "down":
        return "markdown" if direction <= -0.3 else "downtrend_bounce"
    return "range"


def _alignment_label(agreement: float, direction: float) -> str:
    if agreement >= 0.99:
        return "aligned_bull" if direction >= 0 else "aligned_bear"
    return "conflicted"


def _build_symbol(symbol: str, features: dict[str, Any]) -> dict[str, Any]:
    timeframes = features.get("timeframes") or {}
    daily = timeframes.get("daily")
    data_quality = str(features.get("data_quality") or "ok")
    multi = features.get("multi_timeframe") or {}
    rel_strength = multi.get("rel_strength_vs_spy") or {}

    if not isinstance(daily, dict) or data_quality == "failed" or _f(daily.get("last_close")) is None:
        return _avoid_symbol("no usable daily timeframe data; technical engine fail-closed")

    direction, breakdown = _composite_direction(daily, timeframes, rel_strength)
    priority = round(_clamp(50.0 + 50.0 * direction, 0.0, 100.0), 2)
    action = _action_from_priority(priority)

    reasons = [
        f"dir={breakdown['direction']}",
        f"tf={breakdown['per_timeframe']}",
        f"relS={breakdown['rel_strength_dir']}",
    ]
    if breakdown["flags"]:
        reasons.append("flags=" + "/".join(breakdown["flags"]))

    chasing = _is_chasing(daily)
    if chasing and action in _BULLISH_ACTIONS:
        action = "observe"
        priority = min(priority, 50.0)
        reasons.append("chase_guard")

    levels = _build_levels(daily)
    price = levels["price"]
    atr = _f(daily.get("atr_14")) or _atr_fallback(price, levels["range_low"], levels["range_high"])
    atr_pct = _f(daily.get("atr_pct"))
    avg_volume_20 = _f(daily.get("avg_volume_20"))
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

    confidence = _confidence(direction, breakdown["timeframe_agreement"], data_quality, atr_pct, avg_volume_20)
    rationale = f"engine: {', '.join(reasons)}, priority={priority} -> {action} (setup={setup_type})"

    return {
        "technical_phase": _phase(trend, direction),
        "technical_action": action,
        "priority_score": priority,
        "timeframe_stack": {"higher": "1w", "execution": "1d", "lower": "1h"},
        "timeframe_alignment": _alignment_label(breakdown["timeframe_agreement"], direction),
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
            "direction": breakdown["direction"],
            "base_action": action,
            "base_priority": priority,
            "base_confidence": confidence,
            "atr_14": round(atr, 4),
            "atr_pct": round(atr_pct, 2) if atr_pct is not None else None,
            "data_quality": data_quality,
            "breakdown": breakdown,
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
        "engine": {
            "source": "technical_engine",
            "direction": 0.0,
            "base_action": "avoid",
            "base_priority": 0.0,
            "base_confidence": 0.0,
            "atr_14": 0.0,
            "atr_pct": None,
            "data_quality": "failed",
        },
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


# --------------------------------------------------------------------------- #
# Stage 2 — bounded LLM reconciliation
# --------------------------------------------------------------------------- #
def _max_swing() -> float:
    return _f(os.environ.get("TECHNICAL_LLM_MAX_SWING")) or 12.0


def _llm_direction(assessment: dict[str, Any]) -> tuple[float, float, list[str]]:
    """Return (direction[-1,1], conviction[0,1], reasons) from an llm_assessment."""
    reasons: list[str] = []
    components: list[float] = []
    for key in ("bias", "chan_signal", "fundamental_bias"):
        raw = str(assessment.get(key) or "").strip().lower()
        if raw in _BIAS_MAP:
            components.append(_BIAS_MAP[raw])
            if _BIAS_MAP[raw] != 0.0:
                reasons.append(f"{key}={raw}")
    direction = sum(components) / len(components) if components else 0.0

    conviction = _clamp(_f(assessment.get("conviction")) or 0.0, 0.0, 1.0)
    quality = str(assessment.get("brooks_quality") or "").strip().lower()
    if quality == "strong":
        conviction = _clamp(conviction + 0.10, 0.0, 1.0)
    elif quality == "weak":
        conviction = _clamp(conviction - 0.10, 0.0, 1.0)
    return _clamp(direction, -1.0, 1.0), conviction, reasons


def apply_llm_assessment(
    signals_payload: dict[str, Any],
    *,
    max_swing: float | None = None,
) -> dict[str, Any]:
    """Fold each symbol's ``llm_assessment`` into the decision, within bounds.

    Bounds (so a wrong/hallucinated model can never override risk controls):
    - ``priority_score`` moves by at most ``max_swing`` points (default
      ``TECHNICAL_LLM_MAX_SWING`` = 12), which is ≈ one action band;
    - ``veto: true`` is caution-only — it can downgrade to ``avoid`` but can
      never upgrade;
    - price levels, stops, targets and the no-trade zone are NOT modified, so the
      price-policy gate's deterministic risk controls always stand;
    - symbols whose engine data failed (fail-closed ``avoid``) are left untouched.

    Mutates and returns ``signals_payload``.
    """
    swing = max_swing if max_swing is not None else _max_swing()
    symbols = signals_payload.get("symbols")
    if not isinstance(symbols, dict):
        return signals_payload

    for symbol, payload in symbols.items():
        if not isinstance(payload, dict):
            continue
        engine = payload.get("engine") or {}
        if engine.get("data_quality") == "failed":
            continue
        assessment = payload.get("llm_assessment")
        if not isinstance(assessment, dict) or not assessment:
            continue

        base_priority = _f(engine.get("base_priority"))
        if base_priority is None:
            base_priority = _f(payload.get("priority_score")) or 50.0
        base_action = str(engine.get("base_action") or payload.get("technical_action") or "observe")
        base_conf = _f(engine.get("base_confidence"))
        if base_conf is None:
            base_conf = _f(payload.get("confidence")) or 0.0
        engine_dir = _f(engine.get("direction")) or 0.0

        llm_dir, conviction, llm_reasons = _llm_direction(assessment)
        veto = bool(assessment.get("veto"))

        applied: dict[str, Any] = {
            "llm_direction": round(llm_dir, 3),
            "conviction": round(conviction, 3),
            "reasons": llm_reasons,
            "veto": veto,
        }

        if veto:
            new_priority = min(base_priority, 8.0)
            new_action = "avoid"
            new_conf = round(_clamp(min(base_conf, 0.4), 0.0, 0.97), 2)
            applied["delta"] = round(new_priority - base_priority, 2)
            applied["note"] = "llm_veto: caution downgrade"
            # Block trading explicitly: a veto'd symbol should not present a
            # tradeable setup to the price gate.
            payload["no_trade_zone"] = {
                "low": _f(payload.get("key_levels", {}).get("range_low")) or 0.0,
                "high": _f(payload.get("key_levels", {}).get("range_high")) or 999999.0,
                "reason": "llm_veto",
            }
        else:
            delta = _clamp(llm_dir * conviction * swing, -swing, swing)
            new_priority = round(_clamp(base_priority + delta, 0.0, 100.0), 2)
            new_action = _action_from_priority(new_priority)
            # confidence: agree → boost, disagree → cut, both scaled by conviction
            if llm_dir != 0.0 and _sign(llm_dir) == _sign(engine_dir):
                new_conf = base_conf + 0.10 * conviction
            elif llm_dir != 0.0 and _sign(llm_dir) == -_sign(engine_dir):
                new_conf = base_conf - 0.15 * conviction
            else:
                new_conf = base_conf
            new_conf = round(_clamp(new_conf, 0.0, 0.97), 2)
            applied["delta"] = round(new_priority - base_priority, 2)

        payload["technical_action"] = new_action
        payload["priority_score"] = new_priority
        payload["confidence"] = new_conf
        payload["decision_rationale"] = (
            f"{payload.get('decision_rationale', '')} | llm: dir={applied['llm_direction']}, "
            f"conv={applied['conviction']}, delta={applied['delta']} -> {new_action}"
        )
        engine["llm"] = applied
        payload["engine"] = engine

    signals_payload["analysis_status"] = "engine+llm"
    signals_payload["notes"] = (
        "decision-critical signals from technical_engine; action/priority/confidence "
        "reconciled with bounded llm_assessment (price levels unchanged)"
    )
    return signals_payload


def reconcile_technical_signals_file(path: str) -> None:
    """Read a technical_signals JSON file, apply bounded LLM reconciliation, write back.

    Convenience entry point for shell helpers. No-op (engine output retained) if the
    file is missing/unreadable or carries no llm_assessment fields.
    """
    from pathlib import Path

    from trading_agent.core.io import read_json, write_json

    p = Path(path)
    if not p.exists():
        return
    payload = read_json(p)
    if not isinstance(payload, dict):
        return
    write_json(p, apply_llm_assessment(payload))
