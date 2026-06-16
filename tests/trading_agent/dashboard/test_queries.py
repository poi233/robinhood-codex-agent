from __future__ import annotations

import json
from pathlib import Path

from trading_agent.analytics.build_db import build_analytics_db
from trading_agent.core.io import write_json
from trading_agent.dashboard import queries


def _write_jsonl(path: Path, rows: list[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def _make_sample_run(agent_root: Path, run_date: str) -> None:
    run_dir = agent_root / "runtime" / "state" / "runs" / run_date
    paper_dir = run_dir / "paper"
    logs_dir = agent_root / "runtime" / "logs" / "runs" / run_date

    write_json(
        run_dir / "run_manifest.json",
        {"run_date": run_date, "strategy_id": "baseline_v1", "trading_mode": "paper", "effective_risk_tier": 4},
    )
    write_json(
        run_dir / "planner" / "daily_plan.json",
        {"plan_state": "normal", "market_regime": "aggressive_ok"},
    )
    write_json(
        run_dir / "planner" / "risk_overlay.json",
        {
            "market_regime": "aggressive_ok",
            "watchlist_candidates": ["NVDA", "PLTR"],
            "tradable_candidates": ["NVDA"],
        },
    )
    write_json(
        run_dir / "planner" / "candidate_scores.json",
        {
            "symbols": {
                "NVDA": {"score": 66.1, "score_status": "scored", "components": {"technical": 70.0, "catalyst": 55.0, "dsa": 60.0, "kronos": 65.0, "quote": 50.0}},
                "PLTR": {"score": 30.0, "score_status": "scored", "components": {"technical": 20.0, "catalyst": 10.0, "dsa": 5.0, "kronos": 0.0, "quote": 0.0}},
            }
        },
    )
    _write_jsonl(
        logs_dir / "audit" / "decisions.jsonl",
        [
            {
                "timestamp": f"{run_date}T09:31:00",
                "decision": "would_trade",
                "proposed_order": {"symbol": "NVDA", "side": "buy", "setup_type": "breakout", "confidence": 0.8},
                "blocked_reasons": [],
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
                "status": "pending",
                "fill_price": None,
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
                "realized_pnl": 5.0,
            },
        ],
    )
    build_analytics_db(agent_root)


def test_list_run_dates_and_latest_run_date(tmp_path: Path) -> None:
    _make_sample_run(tmp_path, "2026-06-15")

    assert queries.list_run_dates(tmp_path) == ["2026-06-15"]
    assert queries.latest_run_date(tmp_path) == "2026-06-15"


def test_list_run_dates_empty_when_no_runtime_state(tmp_path: Path) -> None:
    assert queries.list_run_dates(tmp_path) == []
    assert queries.latest_run_date(tmp_path) is None


def test_overview_combines_runtime_state_and_analytics_db(tmp_path: Path) -> None:
    _make_sample_run(tmp_path, "2026-06-15")

    result = queries.overview(tmp_path, "2026-06-15")

    assert result["plan_state"] == "normal"
    assert result["market_regime"] == "aggressive_ok"
    assert result["watchlist_count"] == 2
    assert result["tradable_count"] == 1
    assert result["top_score"] == 66.1
    assert result["pending_order_count"] == 1
    assert result["today_pnl"] == 5.0
    assert result["total_equity"] == 1000.0


def test_overview_returns_runtime_state_fields_even_without_analytics_db(tmp_path: Path) -> None:
    run_dir = tmp_path / "runtime" / "state" / "runs" / "2026-06-15"
    write_json(run_dir / "planner" / "daily_plan.json", {"plan_state": "no_trade"})
    write_json(run_dir / "planner" / "risk_overlay.json", {"market_regime": "no_trade"})

    result = queries.overview(tmp_path, "2026-06-15")

    assert result["plan_state"] == "no_trade"
    assert result["market_regime"] == "no_trade"
    assert result["top_score"] is None
    assert result["pending_order_count"] == 0


def test_candidates_table_ranked_by_score_desc(tmp_path: Path) -> None:
    _make_sample_run(tmp_path, "2026-06-15")

    rows = queries.candidates_table(tmp_path, "2026-06-15")

    assert [row["symbol"] for row in rows] == ["NVDA", "PLTR"]
    assert rows[0]["is_watchlist"] == 1
    assert rows[0]["is_tradable"] == 1
    assert rows[1]["is_tradable"] == 0


def test_decisions_timeline_returns_rows_for_run_date(tmp_path: Path) -> None:
    _make_sample_run(tmp_path, "2026-06-15")

    rows = queries.decisions_timeline(tmp_path, "2026-06-15")

    assert len(rows) == 1
    assert rows[0]["decision"] == "would_trade"
    assert rows[0]["symbol"] == "NVDA"


def test_orders_table_returns_rows_for_run_date(tmp_path: Path) -> None:
    _make_sample_run(tmp_path, "2026-06-15")

    rows = queries.orders_table(tmp_path, "2026-06-15")

    assert len(rows) == 1
    assert rows[0]["status"] == "pending"
    assert rows[0]["symbol"] == "NVDA"


def test_replay_summary_delegates_to_replay_module(tmp_path: Path) -> None:
    _make_sample_run(tmp_path, "2026-06-15")

    report = queries.replay_summary(tmp_path)

    assert report["run_dates"] == ["2026-06-15"]
    assert report["fill_rate"]["total_orders"] == 1
