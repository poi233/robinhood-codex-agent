from __future__ import annotations

from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import read_json, write_json
from trading_agent.core.time import PT


def _read_json_or_empty(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = read_json(path)
    return payload if isinstance(payload, dict) else {}


def build_premarket_diagnostics(
    *,
    run_date: str,
    candidate_scores: dict[str, Any],
    risk_overlay: dict[str, Any],
    daily_plan: dict[str, Any],
) -> dict[str, Any]:
    symbols = candidate_scores.get("symbols") or {}
    ranked_items = sorted(
        (
            (symbol, payload)
            for symbol, payload in symbols.items()
            if isinstance(payload, dict) and payload.get("score") is not None
        ),
        key=lambda item: (-float(item[1].get("score", 0) or 0), item[0]),
    )
    scores = [float(payload.get("score", 0) or 0) for _, payload in ranked_items]
    top_candidate = ranked_items[0][0] if ranked_items else None
    top_score = round(scores[0], 2) if scores else None

    component_coverage = {
        component: sum(
            1
            for _, payload in ranked_items
            if bool(((payload.get("diagnostics") or {}).get(component) or {}).get("available"))
        )
        for component in ("dsa", "technical", "kronos", "quote", "catalyst")
    }
    unmapped_technical_actions = sorted(
        {
            str(((payload.get("diagnostics") or {}).get("technical") or {}).get("raw_action"))
            for _, payload in ranked_items
            if str(((payload.get("diagnostics") or {}).get("technical") or {}).get("warning") or "").startswith("unmapped_technical_action:")
        }
    )
    missing_component_warnings = sorted(
        {
            warning
            for _, payload in ranked_items
            for warning in list(payload.get("warnings") or [])
            if str(warning).startswith("missing_component:")
        }
    )
    missing_catalyst_score_count = sum(
        1
        for _, payload in ranked_items
        if bool(((payload.get("diagnostics") or {}).get("catalyst") or {}).get("missing_numeric_score"))
    )

    warnings: list[str] = []
    if unmapped_technical_actions:
        warnings.append(f"technical_actions_unmapped: {', '.join(unmapped_technical_actions)}")
    if ranked_items and missing_catalyst_score_count == len(ranked_items):
        warnings.append("catalyst_scores_missing_for_all_symbols")
    trade_threshold = float(risk_overlay.get("trade_score_threshold", 50.0) or 50.0)
    if top_score is not None and top_score < trade_threshold:
        warnings.append(f"top_score_below_trade_threshold_by_{round(trade_threshold - top_score, 2):.2f}")
    if ranked_items and not list(risk_overlay.get("tradable_candidates") or []):
        warnings.append("scored_candidates_exist_but_none_tradable")

    return {
        "date": run_date,
        "generated_at": datetime.now(tz=PT).isoformat(),
        "candidate_count": len(ranked_items),
        "watchlist_candidate_count": len(list(risk_overlay.get("watchlist_candidates") or [])),
        "tradable_candidate_count": len(list(risk_overlay.get("tradable_candidates") or [])),
        "top_candidate": top_candidate,
        "top_score": top_score,
        "score_distribution": {
            "max": round(max(scores), 2) if scores else None,
            "median": round(median(scores), 2) if scores else None,
            "min": round(min(scores), 2) if scores else None,
        },
        "threshold_values": {
            "watchlist_threshold": float(risk_overlay.get("watchlist_score_threshold", 35.0) or 35.0),
            "trade_threshold": trade_threshold,
        },
        "component_coverage": component_coverage,
        "unmapped_technical_actions": unmapped_technical_actions,
        "missing_catalyst_score_count": missing_catalyst_score_count,
        "missing_component_warnings": missing_component_warnings,
        "final_risk_overlay_state": {
            "market_regime": risk_overlay.get("market_regime"),
            "no_trade_reasons": list(risk_overlay.get("no_trade_reasons") or []),
            "watchlist_candidates": list(risk_overlay.get("watchlist_candidates") or []),
            "tradable_candidates": list(risk_overlay.get("tradable_candidates") or []),
        },
        "final_daily_plan_state": {
            "plan_state": daily_plan.get("plan_state"),
            "market_regime": daily_plan.get("market_regime"),
            "allowed_actions": list(daily_plan.get("allowed_actions") or []),
        },
        "warnings": warnings,
    }


def build_premarket_diagnostics_from_paths(agent_root: Path, run_date: str) -> dict[str, Any]:
    paths = build_runtime_paths(agent_root, run_date=run_date)
    payload = build_premarket_diagnostics(
        run_date=run_date,
        candidate_scores=_read_json_or_empty(paths.candidate_scores_path),
        risk_overlay=_read_json_or_empty(paths.risk_overlay_path),
        daily_plan=_read_json_or_empty(paths.daily_plan_path),
    )
    write_json(paths.premarket_diagnostics_path, payload)
    return payload
