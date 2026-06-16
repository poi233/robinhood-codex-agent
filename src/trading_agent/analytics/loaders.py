from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import read_json
from trading_agent.replay.analysis import collect_decisions, collect_paper_orders


def _read_json_or_empty(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = read_json(path)
    return payload if isinstance(payload, dict) else {}


def _read_jsonl_or_empty(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def load_runs(agent_root: Path, run_dates: list[str]) -> list[dict[str, Any]]:
    """One row per run-date with a run_manifest.json (written by B1)."""
    rows: list[dict[str, Any]] = []
    for run_date in run_dates:
        paths = build_runtime_paths(agent_root, run_date=run_date)
        manifest = _read_json_or_empty(paths.run_state_dir / "run_manifest.json")
        if not manifest:
            continue
        rows.append(
            {
                "run_date": run_date,
                "strategy_id": manifest.get("strategy_id"),
                "git_commit": manifest.get("git_commit"),
                "config_hash": manifest.get("config_hash"),
                "trading_mode": manifest.get("trading_mode"),
                "effective_risk_tier": manifest.get("effective_risk_tier"),
            }
        )
    return rows


def load_candidates(agent_root: Path, run_dates: list[str]) -> list[dict[str, Any]]:
    """One row per (run_date, symbol) scored by the premarket scoring layer.

    is_watchlist/is_tradable come from that same run-date's risk_overlay.json.
    price_setup_score/trade_readiness_score are computed transiently during the
    intraday policy run and not persisted anywhere yet, so they are not columns
    here; technical/catalyst/dsa/kronos/quote component scores from
    candidate_scores.json are used instead.
    """
    rows: list[dict[str, Any]] = []
    for run_date in run_dates:
        paths = build_runtime_paths(agent_root, run_date=run_date)
        scores = _read_json_or_empty(paths.candidate_scores_path)
        symbols = scores.get("symbols")
        if not isinstance(symbols, dict) or not symbols:
            continue
        overlay = _read_json_or_empty(paths.risk_overlay_path)
        watchlist = set(overlay.get("watchlist_candidates") or [])
        tradable = set(overlay.get("tradable_candidates") or [])
        for symbol, payload in symbols.items():
            if not isinstance(payload, dict):
                continue
            components = payload.get("components") or {}
            rows.append(
                {
                    "run_date": run_date,
                    "symbol": symbol,
                    "candidate_score": payload.get("score"),
                    "score_status": payload.get("score_status"),
                    "technical_score": components.get("technical"),
                    "catalyst_score": components.get("catalyst"),
                    "dsa_score": components.get("dsa"),
                    "kronos_score": components.get("kronos"),
                    "quote_score": components.get("quote"),
                    "is_watchlist": 1 if symbol in watchlist else 0,
                    "is_tradable": 1 if symbol in tradable else 0,
                }
            )
    return rows


def load_decisions(agent_root: Path, run_dates: list[str]) -> list[dict[str, Any]]:
    """One row per intraday policy decision, flattening proposed_order."""
    rows: list[dict[str, Any]] = []
    for row in collect_decisions(agent_root, run_dates=run_dates):
        proposed_order = row.get("proposed_order") or {}
        if not isinstance(proposed_order, dict):
            proposed_order = {}
        rows.append(
            {
                "timestamp": row.get("timestamp"),
                "run_date": row.get("_run_date"),
                "decision": row.get("decision"),
                "symbol": proposed_order.get("symbol"),
                "side": proposed_order.get("side"),
                "setup_type": proposed_order.get("setup_type"),
                "blocked_reasons": json.dumps(row.get("blocked_reasons") or []),
                "confidence": proposed_order.get("confidence"),
            }
        )
    return rows


def load_orders(agent_root: Path, run_dates: list[str]) -> list[dict[str, Any]]:
    """One row per paper order, resolved to its final fill/cancel state."""
    rows: list[dict[str, Any]] = []
    for row in collect_paper_orders(agent_root, run_dates=run_dates):
        rows.append(
            {
                "timestamp": row.get("timestamp"),
                "run_date": row.get("_run_date"),
                "order_id": row.get("order_id"),
                "symbol": row.get("symbol"),
                "side": row.get("side"),
                "status": row.get("status"),
                "quantity": row.get("quantity"),
                "limit_price": row.get("limit_price"),
                "fill_price": row.get("fill_price"),
                "notional": row.get("notional"),
                "reason_codes": json.dumps(row.get("reason_codes") or []),
            }
        )
    return rows


def load_paper_equity(agent_root: Path, run_dates: list[str]) -> list[dict[str, Any]]:
    """One row per paper equity-curve checkpoint (day_start/day_end/fills)."""
    rows: list[dict[str, Any]] = []
    for run_date in run_dates:
        paths = build_runtime_paths(agent_root, run_date=run_date)
        for row in _read_jsonl_or_empty(paths.paper_equity_curve_path):
            rows.append(
                {
                    "timestamp": row.get("timestamp"),
                    "run_date": row.get("date", run_date),
                    "event": row.get("event"),
                    "cash": row.get("cash"),
                    "positions_market_value": row.get("positions_market_value"),
                    "total_equity": row.get("total_equity"),
                    "realized_pnl": row.get("realized_pnl"),
                }
            )
    return rows


def load_intraday_rankings(agent_root: Path, run_dates: list[str]) -> list[dict[str, Any]]:
    """One row per ranked candidate per intraday run, from intraday_rankings.jsonl.

    These are the intraday six-component scores (trade_readiness_score / price_setup_score
    + components) the policy ranker computes per run; persisted by the intraday pipeline so
    E1 forward-return attribution and E2 weight calibration have historical data.
    """
    rows: list[dict[str, Any]] = []
    for run_date in run_dates:
        paths = build_runtime_paths(agent_root, run_date=run_date)
        for row in _read_jsonl_or_empty(paths.intraday_rankings_log_path):
            rows.append(
                {
                    "timestamp": row.get("timestamp"),
                    "run_date": row.get("run_date", run_date),
                    "symbol": row.get("symbol"),
                    "trade_readiness_score": row.get("trade_readiness_score"),
                    "price_setup_score": row.get("price_setup_score"),
                    "candidate_score": row.get("candidate_score"),
                    "technical_score": row.get("technical_score"),
                    "research_score": row.get("research_score"),
                    "catalyst_score": row.get("catalyst_score"),
                    "liquidity_score": row.get("liquidity_score"),
                }
            )
    return rows


def load_blocked_reasons(decisions_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate decisions_rows' blocked_reasons into per-(run_date, reason) counts."""
    counts: dict[tuple[str, str], int] = {}
    for row in decisions_rows:
        run_date = str(row.get("run_date") or "")
        try:
            reasons = json.loads(row.get("blocked_reasons") or "[]")
        except json.JSONDecodeError:
            reasons = []
        for reason in reasons:
            key = (run_date, str(reason))
            counts[key] = counts.get(key, 0) + 1
    return [
        {"run_date": run_date, "reason": reason, "count": count}
        for (run_date, reason), count in sorted(counts.items())
    ]
