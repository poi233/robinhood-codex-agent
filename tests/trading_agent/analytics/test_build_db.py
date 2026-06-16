from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from trading_agent.analytics.build_db import build_analytics_db


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def _make_sample_run(agent_root: Path, run_date: str) -> None:
    run_dir = agent_root / "runtime" / "state" / "runs" / run_date
    paper_dir = run_dir / "paper"
    logs_dir = agent_root / "runtime" / "logs" / "runs" / run_date

    _write_json(
        run_dir / "run_manifest.json",
        {
            "run_date": run_date,
            "strategy_id": "baseline_v1",
            "trading_mode": "paper",
            "effective_risk_tier": 4,
            "scoring_profile": "aggressive_growth",
            "policy_profile": "aggressive_growth",
            "active_watchlist_count": 29,
            "git_commit": "deadbeef",
            "config_hash": "abc123",
            "codex_model": "gpt-5.4-mini",
        },
    )
    _write_json(
        run_dir / "planner" / "candidate_scores.json",
        {
            "symbols": {
                "NVDA": {
                    "score": 66.1,
                    "score_status": "scored",
                    "components": {"technical": 70.0, "catalyst": 55.0, "dsa": 60.0, "kronos": 65.0, "quote": 50.0},
                },
                "PLTR": {
                    "score": 30.0,
                    "score_status": "scored",
                    "components": {"technical": 20.0, "catalyst": 10.0, "dsa": 5.0, "kronos": 0.0, "quote": 0.0},
                },
            }
        },
    )
    _write_json(
        run_dir / "planner" / "risk_overlay.json",
        {"watchlist_candidates": ["NVDA", "PLTR"], "tradable_candidates": ["NVDA"]},
    )
    _write_jsonl(
        logs_dir / "audit" / "decisions.jsonl",
        [
            {
                "timestamp": f"{run_date}T09:31:00",
                "decision": "would_trade",
                "action_taken": "paper_fill",
                "proposed_order": {"symbol": "NVDA", "side": "buy", "setup_type": "breakout", "confidence": 0.8},
                "blocked_reasons": [],
            },
            {
                "timestamp": f"{run_date}T09:32:00",
                "decision": "no_trade",
                "action_taken": "none",
                "proposed_order": None,
                "blocked_reasons": ["below_trade_threshold", "low_effective_coverage"],
            },
        ],
    )
    _write_jsonl(
        paper_dir / "orders.jsonl",
        [
            {
                "order_id": "paper-nvda-1",
                "symbol": "NVDA",
                "side": "buy",
                "quantity": 1,
                "limit_price": 100.0,
                "notional": 100.0,
                "status": "filled",
                "fill_price": 100.0,
                "reason_codes": ["breakout"],
                "timestamp": f"{run_date}T09:31:05",
            }
        ],
    )
    _write_jsonl(
        paper_dir / "equity_curve.jsonl",
        [
            {
                "timestamp": f"{run_date}T06:30:00",
                "date": run_date,
                "event": "day_start",
                "cash": 1000.0,
                "positions_market_value": 0.0,
                "total_equity": 1000.0,
                "realized_pnl": 0.0,
            },
            {
                "timestamp": f"{run_date}T13:00:00",
                "date": run_date,
                "event": "day_end",
                "cash": 900.0,
                "positions_market_value": 100.0,
                "total_equity": 1000.0,
                "realized_pnl": 0.0,
            },
        ],
    )


def _query_all(db_path: Path, table: str) -> list[tuple]:
    connection = sqlite3.connect(db_path)
    try:
        return connection.execute(f"SELECT * FROM {table}").fetchall()
    finally:
        connection.close()


def test_build_analytics_db_creates_six_tables_with_correct_row_counts(tmp_path: Path) -> None:
    _make_sample_run(tmp_path, "2026-06-15")

    row_counts = build_analytics_db(tmp_path)

    assert row_counts == {
        "runs": 1,
        "candidates": 2,
        "decisions": 2,
        "orders": 1,
        "paper_equity": 2,
        "blocked_reasons": 2,
    }
    db_path = tmp_path / "runtime" / "analytics" / "analytics.db"
    assert db_path.exists()
    assert len(_query_all(db_path, "runs")) == 1
    assert len(_query_all(db_path, "candidates")) == 2
    assert len(_query_all(db_path, "orders")) == 1


def test_build_analytics_db_is_idempotent_on_rerun(tmp_path: Path) -> None:
    _make_sample_run(tmp_path, "2026-06-15")

    first = build_analytics_db(tmp_path)
    second = build_analytics_db(tmp_path)

    assert first == second
    db_path = tmp_path / "runtime" / "analytics" / "analytics.db"
    assert len(_query_all(db_path, "orders")) == 1


def test_build_analytics_db_joins_watchlist_and_tradable_flags(tmp_path: Path) -> None:
    _make_sample_run(tmp_path, "2026-06-15")

    build_analytics_db(tmp_path)

    db_path = tmp_path / "runtime" / "analytics" / "analytics.db"
    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute(
            "SELECT symbol, is_watchlist, is_tradable FROM candidates ORDER BY symbol"
        ).fetchall()
    finally:
        connection.close()

    assert rows == [("NVDA", 1, 1), ("PLTR", 1, 0)]


def test_build_analytics_db_aggregates_blocked_reasons_per_run_date(tmp_path: Path) -> None:
    _make_sample_run(tmp_path, "2026-06-15")

    build_analytics_db(tmp_path)

    db_path = tmp_path / "runtime" / "analytics" / "analytics.db"
    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute(
            "SELECT run_date, reason, count FROM blocked_reasons ORDER BY reason"
        ).fetchall()
    finally:
        connection.close()

    assert rows == [
        ("2026-06-15", "below_trade_threshold", 1),
        ("2026-06-15", "low_effective_coverage", 1),
    ]


def test_build_analytics_db_handles_run_dates_with_no_data(tmp_path: Path) -> None:
    (tmp_path / "runtime" / "state" / "runs" / "2026-06-15").mkdir(parents=True)

    row_counts = build_analytics_db(tmp_path)

    assert row_counts == {
        "runs": 0,
        "candidates": 0,
        "decisions": 0,
        "orders": 0,
        "paper_equity": 0,
        "blocked_reasons": 0,
    }
