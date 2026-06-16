from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from trading_agent.analytics.build_db import default_analytics_db_path
from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import read_json
from trading_agent.replay.analysis import build_replay_report, discover_run_dates


def _read_json_or_empty(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = read_json(path)
    return payload if isinstance(payload, dict) else {}


def _connect(agent_root: Path) -> sqlite3.Connection | None:
    db_path = default_analytics_db_path(agent_root)
    if not db_path.exists():
        return None
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def _rows_as_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def list_run_dates(agent_root: Path) -> list[str]:
    """Most-recent-first list of run dates with any runtime/state/runs data."""
    return list(reversed(discover_run_dates(agent_root)))


def latest_run_date(agent_root: Path) -> str | None:
    dates = list_run_dates(agent_root)
    return dates[0] if dates else None


def overview(agent_root: Path, run_date: str) -> dict[str, Any]:
    """Top-of-page summary: plan_state/market_regime come straight from the
    run's daily_plan.json/risk_overlay.json (analytics.db doesn't carry them);
    everything else is aggregated from analytics.db.
    """
    paths = build_runtime_paths(agent_root, run_date=run_date)
    daily_plan = _read_json_or_empty(paths.daily_plan_path)
    risk_overlay = _read_json_or_empty(paths.risk_overlay_path)

    result: dict[str, Any] = {
        "run_date": run_date,
        "plan_state": daily_plan.get("plan_state"),
        "market_regime": risk_overlay.get("market_regime") or daily_plan.get("market_regime"),
        "watchlist_count": len(risk_overlay.get("watchlist_candidates") or []),
        "tradable_count": len(risk_overlay.get("tradable_candidates") or []),
        "top_score": None,
        "pending_order_count": 0,
        "today_pnl": None,
        "total_equity": None,
    }

    connection = _connect(agent_root)
    if connection is None:
        return result
    try:
        top_score_row = connection.execute(
            "SELECT MAX(candidate_score) AS top_score FROM candidates WHERE run_date = ?", (run_date,)
        ).fetchone()
        if top_score_row is not None and top_score_row["top_score"] is not None:
            result["top_score"] = round(float(top_score_row["top_score"]), 2)

        pending_row = connection.execute(
            "SELECT COUNT(*) AS pending_count FROM orders WHERE run_date = ? AND status = 'pending'", (run_date,)
        ).fetchone()
        if pending_row is not None:
            result["pending_order_count"] = int(pending_row["pending_count"] or 0)

        equity_row = connection.execute(
            "SELECT realized_pnl, total_equity FROM paper_equity WHERE run_date = ? ORDER BY timestamp DESC LIMIT 1",
            (run_date,),
        ).fetchone()
        if equity_row is not None:
            result["today_pnl"] = equity_row["realized_pnl"]
            result["total_equity"] = equity_row["total_equity"]
    finally:
        connection.close()

    return result


def candidates_table(agent_root: Path, run_date: str) -> list[dict[str, Any]]:
    """Candidates ranked by score, with watchlist/tradable flags and component scores."""
    connection = _connect(agent_root)
    if connection is None:
        return []
    try:
        rows = connection.execute(
            """
            SELECT symbol, candidate_score, score_status, technical_score, catalyst_score,
                   dsa_score, kronos_score, quote_score, is_watchlist, is_tradable
            FROM candidates
            WHERE run_date = ?
            ORDER BY candidate_score DESC
            """,
            (run_date,),
        ).fetchall()
        return _rows_as_dicts(rows)
    finally:
        connection.close()


def decisions_timeline(agent_root: Path, run_date: str) -> list[dict[str, Any]]:
    """Intraday policy decisions for the day, oldest first."""
    connection = _connect(agent_root)
    if connection is None:
        return []
    try:
        rows = connection.execute(
            """
            SELECT timestamp, decision, symbol, side, setup_type, blocked_reasons, confidence
            FROM decisions
            WHERE run_date = ?
            ORDER BY timestamp ASC
            """,
            (run_date,),
        ).fetchall()
        return _rows_as_dicts(rows)
    finally:
        connection.close()


def orders_table(agent_root: Path, run_date: str) -> list[dict[str, Any]]:
    """Paper orders for the day, most recent first."""
    connection = _connect(agent_root)
    if connection is None:
        return []
    try:
        rows = connection.execute(
            """
            SELECT timestamp, order_id, symbol, side, status, quantity, limit_price, fill_price, notional, reason_codes
            FROM orders
            WHERE run_date = ?
            ORDER BY timestamp DESC
            """,
            (run_date,),
        ).fetchall()
        return _rows_as_dicts(rows)
    finally:
        connection.close()


def replay_summary(agent_root: Path, *, since: str | None = None, until: str | None = None) -> dict[str, Any]:
    """Fill-rate + blocked-reason replay report, reusing the existing replay module."""
    return build_replay_report(agent_root, since_date=since, until_date=until)
