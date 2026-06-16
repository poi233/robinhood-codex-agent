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


def growth_observations(agent_root: Path) -> dict[str, Any]:
    """Read-only: runtime/analytics/growth_observations.json (empty if not built yet)."""
    from trading_agent.growth.observations import default_growth_observations_path

    return _read_json_or_empty(default_growth_observations_path(agent_root))


# --- C3 Dashboard v2: richer queries (all read-only, pure) ---

def candidates_with_rankings(agent_root: Path, run_date: str) -> list[dict[str, Any]]:
    """Candidates joined with the latest intraday ranking scores per symbol for the day."""
    connection = _connect(agent_root)
    if connection is None:
        return []
    try:
        rows = connection.execute(
            """
            SELECT c.symbol, c.candidate_score, c.score_status,
                   c.technical_score, c.catalyst_score, c.dsa_score, c.kronos_score, c.quote_score,
                   c.is_watchlist, c.is_tradable,
                   r.trade_readiness_score, r.price_setup_score
            FROM candidates c
            LEFT JOIN (
                SELECT symbol, trade_readiness_score, price_setup_score, MAX(timestamp) AS ts
                FROM intraday_rankings WHERE run_date = ? GROUP BY symbol
            ) r ON c.symbol = r.symbol
            WHERE c.run_date = ?
            ORDER BY c.candidate_score DESC
            """,
            (run_date, run_date),
        ).fetchall()
        return _rows_as_dicts(rows)
    finally:
        connection.close()


def equity_timeseries(agent_root: Path, *, since: str | None = None, until: str | None = None) -> list[dict[str, Any]]:
    """Cross-day paper equity checkpoints, oldest first, for the equity curve chart."""
    connection = _connect(agent_root)
    if connection is None:
        return []
    try:
        rows = connection.execute(
            "SELECT run_date, timestamp, event, cash, positions_market_value, total_equity, realized_pnl "
            "FROM paper_equity ORDER BY timestamp ASC"
        ).fetchall()
    finally:
        connection.close()
    result = _rows_as_dicts(rows)
    if since is not None:
        result = [row for row in result if str(row.get("run_date") or "") >= since]
    if until is not None:
        result = [row for row in result if str(row.get("run_date") or "") <= until]
    return result


def blocked_reason_trend(agent_root: Path) -> list[dict[str, Any]]:
    """Per-(run_date, reason) blocked counts across all run dates, for a stacked trend."""
    connection = _connect(agent_root)
    if connection is None:
        return []
    try:
        rows = connection.execute(
            "SELECT run_date, reason, count FROM blocked_reasons ORDER BY run_date ASC, count DESC"
        ).fetchall()
        return _rows_as_dicts(rows)
    finally:
        connection.close()


def strategy_comparison(agent_root: Path) -> list[dict[str, Any]]:
    """Aggregate analytics.db by strategy_id (from the runs table) into a side-by-side table.

    One row per strategy version that has runs: run days, date range, fill rate, no-trade
    rate, realized PnL, average candidate / trade-readiness score, top blocked reason.
    Run dates with no manifest (no strategy_id) are excluded from the comparison.
    """
    from collections import Counter, defaultdict

    connection = _connect(agent_root)
    if connection is None:
        return []
    try:
        runs = connection.execute("SELECT run_date, strategy_id FROM runs").fetchall()
        orders = connection.execute("SELECT run_date, status FROM orders").fetchall()
        decisions = connection.execute("SELECT run_date, decision FROM decisions").fetchall()
        candidates = connection.execute("SELECT run_date, candidate_score FROM candidates").fetchall()
        rankings = connection.execute("SELECT run_date, trade_readiness_score FROM intraday_rankings").fetchall()
        blocked = connection.execute("SELECT run_date, reason, count FROM blocked_reasons").fetchall()
        equity = connection.execute("SELECT run_date, realized_pnl, timestamp FROM paper_equity ORDER BY timestamp ASC").fetchall()
    finally:
        connection.close()

    run_strategy = {row["run_date"]: row["strategy_id"] for row in runs if row["strategy_id"]}
    if not run_strategy:
        return []

    day_pnl: dict[str, float] = {}
    for row in equity:  # ordered asc, so the last write per run_date wins (day-end)
        if row["realized_pnl"] is not None:
            day_pnl[row["run_date"]] = float(row["realized_pnl"])

    def _blank() -> dict[str, Any]:
        return {"run_dates": set(), "orders_total": 0, "orders_filled": 0, "decisions_total": 0,
                "would_trade": 0, "score_sum": 0.0, "score_n": 0, "tr_sum": 0.0, "tr_n": 0, "reasons": Counter()}

    agg: dict[str, dict[str, Any]] = defaultdict(_blank)
    for run_date, strategy_id in run_strategy.items():
        agg[strategy_id]["run_dates"].add(run_date)

    def _strat(run_date: str) -> str | None:
        return run_strategy.get(run_date)

    for row in orders:
        strat = _strat(row["run_date"])
        if strat is None:
            continue
        agg[strat]["orders_total"] += 1
        if str(row["status"] or "").lower() == "filled":
            agg[strat]["orders_filled"] += 1
    for row in decisions:
        strat = _strat(row["run_date"])
        if strat is None:
            continue
        agg[strat]["decisions_total"] += 1
        if row["decision"] == "would_trade":
            agg[strat]["would_trade"] += 1
    for row in candidates:
        strat = _strat(row["run_date"])
        if strat is None or row["candidate_score"] is None:
            continue
        agg[strat]["score_sum"] += float(row["candidate_score"])
        agg[strat]["score_n"] += 1
    for row in rankings:
        strat = _strat(row["run_date"])
        if strat is None or row["trade_readiness_score"] is None:
            continue
        agg[strat]["tr_sum"] += float(row["trade_readiness_score"])
        agg[strat]["tr_n"] += 1
    for row in blocked:
        strat = _strat(row["run_date"])
        if strat is None:
            continue
        agg[strat]["reasons"][row["reason"]] += int(row["count"] or 0)

    result: list[dict[str, Any]] = []
    for strategy_id, data in agg.items():
        run_dates = sorted(data["run_dates"])
        if not run_dates:
            continue
        total_pnl = sum(day_pnl.get(d, 0.0) for d in run_dates)
        orders_total = data["orders_total"]
        decisions_total = data["decisions_total"]
        top_reason = data["reasons"].most_common(1)
        result.append({
            "strategy_id": strategy_id,
            "run_days": len(run_dates),
            "date_start": run_dates[0],
            "date_end": run_dates[-1],
            "orders_total": orders_total,
            "fill_rate_pct": round(data["orders_filled"] / orders_total * 100, 1) if orders_total else 0.0,
            "no_trade_rate_pct": round((decisions_total - data["would_trade"]) / decisions_total * 100, 1) if decisions_total else 0.0,
            "total_realized_pnl": round(total_pnl, 2),
            "avg_realized_pnl_per_day": round(total_pnl / len(run_dates), 2),
            "avg_candidate_score": round(data["score_sum"] / data["score_n"], 2) if data["score_n"] else None,
            "avg_trade_readiness_score": round(data["tr_sum"] / data["tr_n"], 2) if data["tr_n"] else None,
            "top_blocked_reason": top_reason[0][0] if top_reason else None,
        })
    result.sort(key=lambda item: item["strategy_id"])
    return result


def champion_vs_challengers(agent_root: Path) -> dict[str, Any]:
    """Read-only: the G7 experiment_report.json (champion vs shadow challengers)."""
    from trading_agent.growth.evaluator import default_experiment_report_path

    return _read_json_or_empty(default_experiment_report_path(agent_root))


def proposals_overview(agent_root: Path) -> list[dict[str, Any]]:
    """Read-only summary of every written proposal + its validation status (if any)."""
    base = agent_root / "runtime" / "strategy_proposals"
    if not base.exists():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(base.rglob("proposal_*.json")):
        if path.name.endswith("_validation.json"):
            continue
        payload = _read_json_or_empty(path)
        validation = _read_json_or_empty(path.with_name(f"{path.stem}_validation.json"))
        out.append({
            "date": path.parent.name,
            "proposal_id": payload.get("proposal_id"),
            "mutation": payload.get("mutation"),
            "status": payload.get("status"),
            "validation_status": validation.get("status"),
        })
    return out


def experiment_queue_overview(agent_root: Path) -> list[dict[str, Any]]:
    """Read-only: the shadow-experiment queue (reuses the G5 queue loader)."""
    from trading_agent.growth.experiment_queue import list_experiments

    return list_experiments(agent_root)


def theme_diagnostics(agent_root: Path, run_date: str) -> dict[str, Any]:
    """Read-only: the C2 theme/speculative concentration diagnostics for a run date."""
    paths = build_runtime_paths(agent_root, run_date=run_date)
    payload = _read_json_or_empty(paths.premarket_diagnostics_path)
    return payload.get("theme_diagnostics") or {}
