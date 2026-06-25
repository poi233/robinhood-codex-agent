"""R1 — strategy leaderboard (treat every strategy as a peer; leader = top by P&L, display only).

The challengers already trade in parallel in their own isolated paper ledgers (G9); the champion
trades the main ledger. This assembles all of them into ONE uniform, sorted table so the dashboard
can show them as equals and highlight whichever is most profitable — without changing what actually
trades. The "leader" is a DISPLAY pointer only (top total return that clears the min-filled-trades
guardrail); the execution champion stays a manual, guardrailed decision (G8 / Q5).

Read-only: reads each strategy's equity curve + the evaluator's per-strategy metrics. Champion is
``role='champion'`` keyed by its registry strategy_id; challengers by their experiment strategy_id.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from trading_agent.core.context import build_experiment_runtime_paths, build_runtime_paths
from trading_agent.growth.diversity import _daily_equity_returns, _read_jsonl
from trading_agent.growth.evaluator import _max_drawdown, evaluate_experiments
from trading_agent.growth.policy import load_growth_policy
from trading_agent.replay.analysis import discover_run_dates
from trading_agent.replay.significance import sharpe


def _load_equity_points(agent_root: Path, *, run_dates: list[str], challenger_id: str | None) -> list[dict[str, Any]]:
    """Equity-curve points across run dates for one strategy. ``challenger_id=None`` → champion's
    main paper ledger; otherwise the isolated experiments/<id>/paper ledger."""
    points: list[dict[str, Any]] = []
    for run_date in run_dates:
        if challenger_id is None:
            path = build_runtime_paths(agent_root, run_date=run_date).paper_equity_curve_path
        else:
            path = build_experiment_runtime_paths(agent_root, run_date=run_date, strategy_id=challenger_id).paper_equity_curve_path
        points.extend(_read_jsonl(path))
    points.sort(key=lambda row: str(row.get("timestamp") or ""))
    return points


def _equity_stats(points: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(p["total_equity"]) for p in points if p.get("total_equity") is not None]
    if not values:
        return {"total_return": None, "sharpe": None, "max_drawdown": None, "days": 0, "last_equity": None}
    base, last = values[0], values[-1]
    returns = _daily_equity_returns(points)
    return {
        "total_return": round(last / base - 1.0, 6) if base else None,
        "sharpe": sharpe(list(returns.values())),
        "max_drawdown": _max_drawdown(values),
        "days": len(values),
        "last_equity": round(last, 2),
    }


def _row(strategy_id: str, role: str, equity_points: list[dict[str, Any]], metrics: dict[str, Any]) -> dict[str, Any]:
    stats = _equity_stats(equity_points)
    drawdown = metrics.get("max_drawdown")
    return {
        "strategy_id": strategy_id,
        "role": role,
        "total_return": stats["total_return"],
        "sharpe": stats["sharpe"],
        "max_drawdown": drawdown if drawdown is not None else stats["max_drawdown"],
        "filled": int(metrics.get("filled") or 0),
        "fill_rate_pct": metrics.get("fill_rate_pct"),
        "realized_pnl": metrics.get("realized_pnl"),
        "days": stats["days"],
        "last_equity": stats["last_equity"],
    }


def _sort_key(row: dict[str, Any]) -> tuple[bool, float]:
    tr = row["total_return"]
    return (tr is not None, tr if tr is not None else float("-inf"))


def build_leaderboard(agent_root: Path, *, since: str | None = None, until: str | None = None) -> dict[str, Any]:
    """All strategies (champion + active_shadow challengers) in one table, sorted by total paper
    return. ``leader`` = the top row that also clears the min-filled-trades guardrail (display only)."""
    from trading_agent.strategy.registry import load_active_strategy

    run_dates = discover_run_dates(agent_root, since_date=since, until_date=until)
    report = evaluate_experiments(agent_root, since=since, until=until)
    champion_id = str(load_active_strategy(agent_root).get("strategy_id") or "champion")
    min_filled = int((load_growth_policy(agent_root).get("promotion_rules") or {}).get("min_filled_trades") or 0)

    rows: list[dict[str, Any]] = [
        _row(champion_id, "champion", _load_equity_points(agent_root, run_dates=run_dates, challenger_id=None), report.get("champion") or {})
    ]
    for challenger in report.get("challengers") or []:
        sid = str(challenger.get("challenger_strategy_id"))
        rows.append(_row(sid, "challenger", _load_equity_points(agent_root, run_dates=run_dates, challenger_id=sid), challenger.get("metrics") or {}))

    rows.sort(key=_sort_key, reverse=True)

    leader_id: str | None = None
    for row in rows:
        if row["total_return"] is not None and row["filled"] >= min_filled:
            leader_id = row["strategy_id"]
            break
    for row in rows:
        row["is_leader"] = row["strategy_id"] == leader_id

    return {
        "generated_at": report.get("generated_at"),
        "champion_id": champion_id,
        "min_filled_trades": min_filled,
        "leader": leader_id,
        "leader_qualified": leader_id is not None,
        "strategies": rows,
        "note": (
            "sorted by total paper-equity return; leader = top return that clears the "
            "min-filled-trades guardrail — DISPLAY ONLY, the execution champion stays manual (G8)."
        ),
    }
