from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import read_json
from trading_agent.replay.forward_returns import DEFAULT_HORIZONS, ForwardReturnRecord

DEFAULT_MARGIN = 5.0
_DEFAULT_THRESHOLD = 50.0


def load_trade_thresholds(agent_root: Path, run_dates: list[str]) -> dict[str, float]:
    """Per run date, the trade-score threshold that gated tradability (from risk_overlay.json,
    falling back to a conservative default). Used to classify near-threshold candidates."""
    thresholds: dict[str, float] = {}
    for run_date in run_dates:
        overlay_path = build_runtime_paths(agent_root, run_date=run_date).risk_overlay_path
        threshold = _DEFAULT_THRESHOLD
        if overlay_path.exists():
            payload = read_json(overlay_path)
            if isinstance(payload, dict):
                value = payload.get("trade_score_threshold")
                try:
                    threshold = float(value)
                except (TypeError, ValueError):
                    threshold = _DEFAULT_THRESHOLD
        thresholds[run_date] = threshold
    return thresholds


def _summarize(returns: list[float]) -> dict[str, Any]:
    if not returns:
        return {"count": 0, "mean_return": None, "hit_rate": None}
    return {
        "count": len(returns),
        "mean_return": round(sum(returns) / len(returns), 6),
        "hit_rate": round(sum(1 for r in returns if r > 0) / len(returns), 4),
    }


def near_threshold_analysis(
    records: list[ForwardReturnRecord],
    thresholds: dict[str, float],
    *,
    margin: float = DEFAULT_MARGIN,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
) -> dict[str, dict[str, dict[str, Any]]]:
    """Classify each candidate by its score vs that day's trade threshold, then compare forward
    returns across classes — the direct test for "is trade_threshold too strict?":

      cleared   : score >= threshold (would trade)
      near_miss : threshold - margin <= score < threshold (just missed the gate)
      below     : score < threshold - margin

    If near_miss returns ≈ or > cleared returns, the gate is probably costing you winners.
    Returns {horizon: {class: {count, mean_return, hit_rate}}}.
    """
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for horizon in horizons:
        buckets: dict[str, list[float]] = defaultdict(list)
        for rec in records:
            score = rec.candidate_score
            ret = rec.returns.get(horizon)
            if score is None or ret is None:
                continue
            threshold = thresholds.get(rec.run_date, _DEFAULT_THRESHOLD)
            if score >= threshold:
                buckets["cleared"].append(ret)
            elif score >= threshold - margin:
                buckets["near_miss"].append(ret)
            else:
                buckets["below"].append(ret)
        out[str(horizon)] = {cls: _summarize(buckets.get(cls, [])) for cls in ("cleared", "near_miss", "below")}
    return out
