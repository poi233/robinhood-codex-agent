from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from trading_agent.core.io import read_json


def _float_list(values: list[object]) -> list[float]:
    result: list[float] = []
    for value in values:
        try:
            result.append(round(float(value), 4))
        except (TypeError, ValueError):
            continue
    return result


def _build_levels_from_rows(rows: list[dict[str, object]]) -> dict[str, object]:
    if not rows:
        return {
            "reference_price": 0.0,
            "supports": [0.0],
            "resistances": [999999.0],
            "range_low": 0.0,
            "range_high": 999999.0,
            "long_trigger": 999999.0,
            "short_trigger": 0.0,
        }

    closes = _float_list([row.get("close") for row in rows])
    highs = _float_list([row.get("high") for row in rows])
    lows = _float_list([row.get("low") for row in rows])
    recent_highs = _float_list([row.get("high") for row in rows[-5:]])
    recent_lows = _float_list([row.get("low") for row in rows[-5:]])

    reference_price = closes[-1] if closes else 0.0
    range_low = min(lows) if lows else 0.0
    range_high = max(highs) if highs else 999999.0
    support_1 = min(recent_lows) if recent_lows else range_low
    support_2 = range_low
    resistance_1 = max(recent_highs) if recent_highs else range_high
    resistance_2 = range_high

    return {
        "reference_price": reference_price,
        "supports": sorted({round(support_1, 4), round(support_2, 4)}),
        "resistances": sorted({round(resistance_1, 4), round(resistance_2, 4)}),
        "range_low": round(range_low, 4),
        "range_high": round(range_high, 4),
        "long_trigger": round(resistance_1, 4),
        "short_trigger": round(support_1, 4),
    }


def build_failed_technical_payload(
    manifest: dict[str, object],
    *,
    run_date: str,
    reason: str,
) -> dict[str, object]:
    requested_symbols = manifest.get("requested_symbols", [])
    ohlcv_root_value = (manifest.get("artifacts") or {}).get("ohlcv_root", "")
    ohlcv_root = Path(str(ohlcv_root_value)) if ohlcv_root_value else None
    manifest_path = ohlcv_root.parent / "manifest.json" if ohlcv_root else Path("state/market_feed") / run_date / "manifest.json"

    symbols: dict[str, object] = {}
    for symbol in requested_symbols:
        if not isinstance(symbol, str) or not symbol.strip():
            continue
        rows: list[dict[str, object]] = []
        if ohlcv_root:
            daily_path = ohlcv_root / symbol / "daily.json"
            if daily_path.exists():
                payload = read_json(daily_path)
                if isinstance(payload, list):
                    rows = [row for row in payload if isinstance(row, dict)]

        levels = _build_levels_from_rows(rows)
        reference_price = float(levels["reference_price"])
        range_low = float(levels["range_low"])
        range_high = float(levels["range_high"])
        long_trigger = float(levels["long_trigger"])
        short_trigger = float(levels["short_trigger"])

        symbols[symbol] = {
            "technical_phase": "unclear",
            "technical_action": "avoid",
            "priority_score": 0,
            "timeframe_stack": {"higher": "1w", "execution": "1d", "lower": "1h"},
            "timeframe_alignment": "conflicted",
            "key_levels": {
                "reference_price": reference_price,
                "supports": levels["supports"],
                "resistances": levels["resistances"],
                "range_low": range_low,
                "range_high": range_high,
            },
            "long_setup": {
                "status": "invalid",
                "setup_type": "none",
                "trigger_above": long_trigger,
                "entry_zone": {"low": max(range_low, short_trigger), "high": max(range_low, short_trigger)},
                "invalidation_below": short_trigger,
                "target_1": long_trigger,
                "target_2": range_high,
                "do_not_chase_above": range_high,
                "notes": reason,
            },
            "short_setup": {
                "status": "invalid",
                "setup_type": "none",
                "trigger_below": short_trigger,
                "entry_zone": {"low": short_trigger, "high": short_trigger},
                "invalidation_above": long_trigger,
                "target_1": short_trigger,
                "target_2": range_low,
                "do_not_chase_below": range_low,
                "notes": "Risk-reduction only for existing longs; never permission to open a short.",
            },
            "no_trade_zone": {
                "low": min(reference_price, long_trigger),
                "high": max(reference_price, short_trigger, long_trigger),
                "reason": reason,
            },
            "chan": {
                "signal": "none",
                "state": "reversal_attempt",
                "invalidation": reason,
                "next_confirmation": "Require completed technical research before taking a setup.",
            },
            "brooks": {
                "setup": "none",
                "entry_style": "none",
                "target_logic": "none",
                "downgrade_condition": reason,
            },
            "fundamentals": {
                "event_bias": "neutral",
                "event_type": "none",
                "quality_flag": "watch",
            },
            "decision_rationale": reason,
            "confidence": 0.0,
        }

    return {
        "date": run_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_feed_manifest": str(manifest_path),
        "analysis_status": "failed",
        "symbols": symbols,
        "notes": reason,
    }
