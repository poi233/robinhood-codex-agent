from __future__ import annotations

import json
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


def _read_jsonl_or_empty(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


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


def calibration_report(agent_root: Path) -> dict[str, Any]:
    """Read-only: the E1 calibration_report.json (empty until `analytics calibrate` is run)."""
    from trading_agent.replay.calibration import default_calibration_report_path

    return _read_json_or_empty(default_calibration_report_path(agent_root))


def fill_quality_report(agent_root: Path) -> dict[str, Any]:
    """Read-only: the E4 fill_quality_report.json (empty until `analytics fill-quality` is run)."""
    from trading_agent.replay.fill_quality import default_fill_quality_report_path

    return _read_json_or_empty(default_fill_quality_report_path(agent_root))


def ai_signal_study(agent_root: Path) -> dict[str, Any]:
    """Read-only: the H3 ai_signal_study.json (empty until `analytics ai-signal-study` is run)."""
    from trading_agent.replay.ai_signal_study import default_ai_signal_study_path

    return _read_json_or_empty(default_ai_signal_study_path(agent_root))


def ai_ablation(agent_root: Path) -> dict[str, Any]:
    """Read-only: the H3 ai_ablation.json (empty until `analytics ai-ablation` is run)."""
    from trading_agent.replay.ai_ablation import default_ai_ablation_path

    return _read_json_or_empty(default_ai_ablation_path(agent_root))


def analysis_history_dates(agent_root: Path) -> list[str]:
    """Read-only: dates (newest first) that have an I2 nightly snapshot under analytics/history/."""
    root = agent_root / "runtime" / "analytics" / "history"
    if not root.exists():
        return []
    dates = [d.name for d in root.iterdir() if d.is_dir() and (d / "nightly_summary.json").exists()]
    return sorted(dates, reverse=True)


def analysis_snapshot(agent_root: Path, date: str) -> dict[str, Any]:
    """Read-only: one night's nightly_summary.json (I2), empty if that date wasn't snapshotted."""
    return _read_json_or_empty(agent_root / "runtime" / "analytics" / "history" / date / "nightly_summary.json")


def analysis_trend(agent_root: Path, *, since: str | None = None, until: str | None = None) -> dict[str, Any]:
    """Read-only: the I3 per-metric time series (reuses build_trend — one calc, shared with the CLI)."""
    from trading_agent.analytics.trend import build_trend

    return build_trend(agent_root, since=since, until=until)


def nightly_health(agent_root: Path) -> dict[str, Any]:
    """Read-only: the L4 nightly_health.json (report freshness + last run's failed steps)."""
    from trading_agent.analytics.nightly_health import default_nightly_health_path

    return _read_json_or_empty(default_nightly_health_path(agent_root))


def portfolio_target(agent_root: Path, run_date: str) -> dict[str, Any]:
    """Read-only: the K1 portfolio_target.json for a run date (current concentration vs target caps)."""
    from trading_agent.portfolio.target import default_portfolio_target_path

    return _read_json_or_empty(default_portfolio_target_path(agent_root, run_date))


def regime_state(agent_root: Path, run_date: str) -> dict[str, Any]:
    """Read-only: the K2 regime_state.json for a run date (quantitative regime + position multiplier)."""
    from trading_agent.regime.engine import default_regime_state_path

    return _read_json_or_empty(default_regime_state_path(agent_root, run_date))


def factor_alpha(agent_root: Path, run_date: str) -> dict[str, Any]:
    """Read-only: the H2 factor_alpha.json for a run date (empty if premarket hasn't produced it)."""
    return _read_json_or_empty(build_runtime_paths(agent_root, run_date=run_date).factor_alpha_path)


def advisory_overlay_summary(agent_root: Path, run_date: str) -> list[dict[str, Any]]:
    """Read-only: per-symbol M-stage overlay impact from intraday_rankings.jsonl."""
    paths = build_runtime_paths(agent_root, run_date=run_date)
    rows: list[dict[str, Any]] = []
    for row in _read_jsonl_or_empty(paths.intraday_rankings_log_path):
        overlay = row.get("advisory_overlay") if isinstance(row.get("advisory_overlay"), dict) else {}
        components = overlay.get("components") if isinstance(overlay.get("components"), dict) else {}
        factor = components.get("factor_alpha") if isinstance(components.get("factor_alpha"), dict) else {}
        ai = components.get("ai") if isinstance(components.get("ai"), dict) else {}
        regime = components.get("regime") if isinstance(components.get("regime"), dict) else {}
        portfolio = components.get("portfolio") if isinstance(components.get("portfolio"), dict) else {}
        ai_layers = []
        for layer, payload in ai.items():
            if not isinstance(payload, dict):
                continue
            direction = payload.get("direction") or "?"
            confidence = payload.get("confidence")
            ai_layers.append(f"{layer}:{direction}@{confidence}" if confidence is not None else f"{layer}:{direction}")
        blocked = overlay.get("blocked_reasons") or []
        portfolio_bits = []
        if portfolio.get("position_weight") is not None:
            portfolio_bits.append(f"position_weight={portfolio.get('position_weight')}")
        if portfolio.get("theme"):
            portfolio_bits.append(f"theme={portfolio.get('theme')}")
        rows.append({
            "timestamp": row.get("timestamp"),
            "symbol": row.get("symbol"),
            "base_trade_readiness_score": row.get("base_trade_readiness_score"),
            "advisory_rank_delta": row.get("advisory_rank_delta", overlay.get("rank_delta")),
            "final_trade_readiness_score": row.get("trade_readiness_score"),
            "size_multiplier": overlay.get("size_multiplier"),
            "block_buy": bool(overlay.get("block_buy", False)),
            "blocked_reasons": ", ".join(str(reason) for reason in blocked),
            "factor_alpha_score": factor.get("score"),
            "ai_layers": ", ".join(ai_layers),
            "regime": str(regime.get("regime") or ""),
            "portfolio": ", ".join(portfolio_bits),
        })
    return rows


def overview_with_delta(agent_root: Path, run_date: str) -> dict[str, Any]:
    """Current run-date overview + the previous run-date overview, for day-over-day deltas.

    Read-only (reuses ``overview``). Returns {"curr", "prev", "prev_run_date"}; ``prev`` is an
    empty dict when there is no earlier run date.
    """
    dates = list_run_dates(agent_root)  # most-recent-first
    curr = overview(agent_root, run_date)
    prev_run_date: str | None = None
    if run_date in dates:
        idx = dates.index(run_date)
        if idx + 1 < len(dates):
            prev_run_date = dates[idx + 1]
    prev = overview(agent_root, prev_run_date) if prev_run_date else {}
    return {"curr": curr, "prev": prev, "prev_run_date": prev_run_date}


def equity_with_benchmark(agent_root: Path, *, benchmark: str = "SPY") -> dict[str, Any]:
    """Paper equity curve with a SPY benchmark normalized to the same starting equity.

    Read-only and fully local: SPY daily closes come from the latest run's market_feed
    ``ohlcv/<benchmark>/daily.json`` (a ~1y history), aligned to each equity point's run_date.
    Returns {"series": [{timestamp, run_date, total_equity, benchmark_equity}], "benchmark",
    "strategy_return_pct", "benchmark_return_pct"}. ``benchmark_equity`` is None where no SPY
    close is available for that date (e.g. market_feed pruned).
    """
    series = equity_timeseries(agent_root)
    out: dict[str, Any] = {
        "series": [],
        "benchmark": benchmark,
        "strategy_return_pct": None,
        "benchmark_return_pct": None,
    }
    points = [row for row in series if row.get("total_equity") is not None and row.get("run_date")]
    if not points:
        return out

    latest = list_run_dates(agent_root)
    spy_close_by_date: dict[str, float] = {}
    if latest:
        feed_dir = build_runtime_paths(agent_root, run_date=latest[0]).market_feed_dir
        spy_rows = feed_dir / "ohlcv" / benchmark / "daily.json"
        if spy_rows.exists():
            try:
                rows = read_json(spy_rows)
            except Exception:
                rows = None
            if isinstance(rows, list):
                for row in rows:
                    ts = str(row.get("timestamp") or "")[:10]
                    close = row.get("close")
                    if ts and close is not None:
                        try:
                            spy_close_by_date[ts] = float(close)
                        except (TypeError, ValueError):
                            continue

    start_equity = float(points[0]["total_equity"])
    start_spy = spy_close_by_date.get(str(points[0]["run_date"]))
    enriched: list[dict[str, Any]] = []
    for row in points:
        spy_close = spy_close_by_date.get(str(row["run_date"]))
        bench_equity = (
            round(start_equity * (spy_close / start_spy), 2)
            if start_spy and spy_close is not None
            else None
        )
        enriched.append({
            "timestamp": row.get("timestamp"),
            "run_date": row.get("run_date"),
            "total_equity": row.get("total_equity"),
            "benchmark_equity": bench_equity,
        })
    out["series"] = enriched

    end_equity = float(points[-1]["total_equity"])
    if start_equity:
        out["strategy_return_pct"] = round((end_equity / start_equity - 1) * 100, 2)
    end_spy = spy_close_by_date.get(str(points[-1]["run_date"]))
    if start_spy and end_spy:
        out["benchmark_return_pct"] = round((end_spy / start_spy - 1) * 100, 2)
    return out


def thesis_attribution(agent_root: Path) -> dict[str, Any]:
    """Read-only: K3 thesis_attribution.json (per-thesis win rate / mean return)."""
    from trading_agent.replay.thesis import default_thesis_path

    return _read_json_or_empty(default_thesis_path(agent_root))


def thesis_trend(agent_root: Path) -> dict[str, Any]:
    """Read-only: per-thesis win-rate time series from archived history/<date>/thesis_attribution.json.

    Returns {thesis: [{date, win_rate, mean_return, count}, ...]} sorted by date ascending, so the
    dashboard can plot how each thesis's win rate evolves as paper samples accumulate. Empty when
    no nightly snapshots have archived a thesis report yet.
    """
    root = agent_root / "runtime" / "analytics" / "history"
    if not root.exists():
        return {}
    series: dict[str, list[dict[str, Any]]] = {}
    for date_dir in sorted(d for d in root.iterdir() if d.is_dir()):
        report = _read_json_or_empty(date_dir / "thesis_attribution.json")
        for row in report.get("theses") or []:
            thesis = row.get("thesis")
            if not thesis:
                continue
            series.setdefault(str(thesis), []).append({
                "date": date_dir.name,
                "win_rate": row.get("win_rate"),
                "mean_return": row.get("mean_return"),
                "count": row.get("count"),
            })
    return series


# --- K线复盘 (candlestick review) — all read-only ------------------------

def _ohlcv_root(agent_root: Path) -> Path | None:
    """The latest run's market_feed ohlcv/ dir (a ~1y daily history per symbol)."""
    latest = list_run_dates(agent_root)
    if not latest:
        return None
    return build_runtime_paths(agent_root, run_date=latest[0]).market_feed_dir / "ohlcv"


def available_kline_symbols(agent_root: Path) -> list[str]:
    """Symbols that have local daily OHLCV (so a candlestick chart can be drawn)."""
    root = _ohlcv_root(agent_root)
    if root is None or not root.exists():
        return []
    return sorted(d.name for d in root.iterdir() if d.is_dir() and (d / "daily.json").exists())


def ohlcv_daily(agent_root: Path, symbol: str) -> list[dict[str, Any]]:
    """Read-only daily OHLCV rows ({timestamp, open, high, low, close, volume}) for one symbol,
    oldest first. Empty when the symbol has no local market_feed history."""
    root = _ohlcv_root(agent_root)
    if root is None:
        return []
    path = root / symbol / "daily.json"
    if not path.exists():
        return []
    try:
        rows = read_json(path)
    except Exception:
        return []
    if not isinstance(rows, list):
        return []
    return sorted((r for r in rows if isinstance(r, dict)), key=lambda r: str(r.get("timestamp") or ""))


def _filled_trades(rows: list[dict[str, Any]], symbol: str) -> list[dict[str, Any]]:
    trades: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("symbol") or "").upper() != symbol.upper():
            continue
        if str(row.get("status") or "").lower() != "filled":
            continue
        price = row.get("fill_price")
        if price is None:
            price = row.get("limit_price")
        reasons = row.get("reason_codes") or []
        trades.append({
            "date": str(row.get("timestamp") or "")[:10],
            "timestamp": row.get("timestamp"),
            "side": str(row.get("side") or "").lower(),
            "price": price,
            "quantity": row.get("quantity"),
            "reason": "、".join(str(r) for r in reasons) if isinstance(reasons, list) else str(reasons),
        })
    return trades


def trades_for_symbol(agent_root: Path, symbol: str) -> dict[str, list[dict[str, Any]]]:
    """Per-strategy filled trades for one symbol across all run dates.

    Read-only. Returns {strategy_label: [{date, timestamp, side, price, quantity, reason}, ...]}.
    The champion ledger lives at ``<run>/paper/orders.jsonl``; each challenger's isolated G9
    ledger lives at ``<run>/experiments/<strategy_id>/paper/orders.jsonl``. Champion is keyed by
    "champion"; challengers by their strategy_id, so the chart can overlay how different strategies
    traded the same stock.
    """
    result: dict[str, list[dict[str, Any]]] = {}
    for run_date in reversed(list_run_dates(agent_root)):  # oldest first
        paths = build_runtime_paths(agent_root, run_date=run_date)
        champ = _filled_trades(_read_jsonl_or_empty(paths.paper_orders_log_path), symbol)
        if champ:
            result.setdefault("champion", []).extend(champ)
        exp_root = paths.run_state_dir / "experiments"
        if exp_root.exists():
            for sid_dir in sorted(d for d in exp_root.iterdir() if d.is_dir()):
                trades = _filled_trades(
                    _read_jsonl_or_empty(sid_dir / "paper" / "orders.jsonl"), symbol
                )
                if trades:
                    result.setdefault(sid_dir.name, []).extend(trades)
    return result

