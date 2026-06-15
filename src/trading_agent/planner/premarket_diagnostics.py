from __future__ import annotations

from collections import Counter
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


def _as_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _ranked_candidates(candidate_scores: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    symbols = candidate_scores.get("symbols") or {}
    ranked = [
        (symbol, payload)
        for symbol, payload in symbols.items()
        if isinstance(payload, dict)
    ]
    ranked.sort(key=lambda item: (-float(item[1].get("score", 0) or 0), item[0]))
    return ranked


def _component_coverage(ranked_items: list[tuple[str, dict[str, Any]]], *, required_components: tuple[str, ...]) -> dict[str, int]:
    return {
        component: sum(
            1
            for _, payload in ranked_items
            if bool(((payload.get("diagnostics") or {}).get(component) or {}).get("available"))
        )
        for component in required_components
    }


def build_premarket_diagnostics(
    *,
    run_date: str,
    candidate_scores: dict[str, Any],
    risk_overlay: dict[str, Any],
    daily_plan: dict[str, Any],
    data_status_summary: dict[str, Any] | None = None,
    catalyst_snapshot: dict[str, Any] | None = None,
    technical_signals: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ranked_items = _ranked_candidates(candidate_scores)
    scored_items = [
        (symbol, payload)
        for symbol, payload in ranked_items
        if payload.get("score") is not None
    ]
    scores = [float(payload.get("score", 0) or 0) for _, payload in scored_items]
    top_candidate = scored_items[0][0] if scored_items else None
    top_score = round(scores[0], 2) if scores else None

    components = ("dsa", "technical", "kronos", "quote", "catalyst")
    component_coverage = _component_coverage(scored_items, required_components=components)
    score_status_counts = dict(
        sorted(
            Counter(str((payload.get("score_status") or "unknown")) for _, payload in ranked_items).items()
        )
    )
    unmapped_technical_actions = sorted(
        {
            str(((payload.get("diagnostics") or {}).get("technical") or {}).get("raw_action"))
            for _, payload in scored_items
            if str(((payload.get("diagnostics") or {}).get("technical") or {}).get("warning") or "").startswith(
                "unmapped_technical_action:"
            )
        }
    )
    missing_component_warnings = sorted(
        {
            str(warning)
            for _, payload in ranked_items
            for warning in list(payload.get("warnings") or [])
            if str(warning).startswith("missing_component:")
        }
    )

    catalyst_symbols = (catalyst_snapshot or {}).get("symbols") or {}
    candidate_symbol_names = [symbol for symbol, _ in ranked_items]
    missing_catalyst_score_count = 0
    for symbol in candidate_symbol_names:
        diag = ((candidate_scores.get("symbols") or {}).get(symbol) or {}).get("diagnostics") or {}
        catalyst_diag = (diag.get("catalyst") or {}) if isinstance(diag, dict) else {}
        catalyst_payload = (catalyst_symbols.get(symbol) or {}) if isinstance(catalyst_symbols, dict) else {}
        if catalyst_diag.get("missing_numeric_score") or (
            catalyst_payload
            and catalyst_payload.get("catalyst_score") is None
            and catalyst_payload.get("score") is None
        ):
            missing_catalyst_score_count += 1

    watchlist_candidates = list(risk_overlay.get("watchlist_candidates") or [])
    tradable_candidates = list(risk_overlay.get("tradable_candidates") or [])
    scored_candidate_count = len(scored_items)
    watchlist_threshold = _as_float(risk_overlay.get("watchlist_score_threshold"), 35.0) or 35.0
    trade_threshold = _as_float(risk_overlay.get("trade_score_threshold"), 50.0) or 50.0

    warnings: list[str] = []
    if unmapped_technical_actions:
        warnings.append(f"technical_actions_unmapped:{','.join(unmapped_technical_actions)}")
    if scored_candidate_count and missing_catalyst_score_count == scored_candidate_count:
        warnings.append("catalyst_scores_missing_for_all_symbols")
    if top_score is not None and top_score < trade_threshold:
        warnings.append(f"top_score_below_trade_threshold_by:{round(trade_threshold - top_score, 2):.2f}")
    if scored_candidate_count and not tradable_candidates:
        warnings.append("scored_candidates_exist_but_none_tradable")
    if watchlist_candidates and daily_plan and str(daily_plan.get("plan_state") or "") == "no_trade":
        warnings.append("watchlist_candidates_exist_but_daily_plan_no_trade")
    if any(str(status) == "insufficient_data" for status in score_status_counts):
        high_insufficient = [
            symbol
            for symbol, payload in scored_items
            if str(payload.get("score_status") or "") == "insufficient_data"
            and float(payload.get("score", 0) or 0) >= trade_threshold
        ]
        if high_insufficient:
            warnings.append(f"high_score_but_insufficient_data:{','.join(high_insufficient)}")

    final_risk_overlay_state = {
        "market_regime": risk_overlay.get("market_regime"),
        "risk_level": risk_overlay.get("risk_level"),
        "allowed_actions": list(risk_overlay.get("allowed_actions") or []),
        "no_trade_reasons": list(risk_overlay.get("no_trade_reasons") or []),
        "today_watchlist": list(risk_overlay.get("today_watchlist") or []),
        "watchlist_candidates": watchlist_candidates,
        "tradable_candidates": tradable_candidates,
    }
    final_daily_plan_state = None
    if daily_plan:
        final_daily_plan_state = {
            "plan_state": daily_plan.get("plan_state"),
            "market_regime": daily_plan.get("market_regime"),
            "allowed_actions": list(daily_plan.get("allowed_actions") or []),
            "today_watchlist": list(daily_plan.get("today_watchlist") or []),
            "no_trade_reasons": list(daily_plan.get("no_trade_reasons") or []),
        }

    return {
        "run_date": run_date,
        "generated_at": datetime.now(tz=PT).isoformat(),
        "candidate_count": len(ranked_items),
        "scored_candidate_count": scored_candidate_count,
        "watchlist_candidate_count": len(watchlist_candidates),
        "tradable_candidate_count": len(tradable_candidates),
        "top_candidate": top_candidate,
        "top_score": top_score,
        "score_distribution": {
            "max": round(max(scores), 2) if scores else None,
            "median": round(median(scores), 2) if scores else None,
            "min": round(min(scores), 2) if scores else None,
        },
        "thresholds": {
            "watchlist_threshold": watchlist_threshold,
            "trade_threshold": trade_threshold,
        },
        "component_coverage": component_coverage,
        "unmapped_technical_actions": unmapped_technical_actions,
        "missing_catalyst_score_count": missing_catalyst_score_count,
        "missing_component_warnings": missing_component_warnings,
        "score_status_counts": score_status_counts,
        "data_status_summary": {
            "execution_blocking": bool((data_status_summary or {}).get("execution_blocking")),
            "reason_codes": list((data_status_summary or {}).get("reason_codes") or []),
        },
        "technical_signal_count": len(list(((technical_signals or {}).get("symbols") or {}).keys())),
        "final_risk_overlay_state": final_risk_overlay_state,
        "final_daily_plan_state": final_daily_plan_state,
        "warnings": warnings,
    }


def build_premarket_diagnostics_from_paths(agent_root: Path, run_date: str) -> dict[str, Any]:
    paths = build_runtime_paths(agent_root, run_date=run_date)
    payload = build_premarket_diagnostics(
        run_date=run_date,
        candidate_scores=_read_json_or_empty(paths.candidate_scores_path),
        risk_overlay=_read_json_or_empty(paths.risk_overlay_path),
        daily_plan=_read_json_or_empty(paths.daily_plan_path),
        data_status_summary=_read_json_or_empty(paths.data_status_summary_path),
        catalyst_snapshot=_read_json_or_empty(paths.catalyst_snapshot_path),
        technical_signals=_read_json_or_empty(paths.technical_signals_path),
    )
    write_json(paths.premarket_diagnostics_path, payload)
    return payload
