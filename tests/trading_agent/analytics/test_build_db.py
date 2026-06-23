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
            "codex_model": "gpt-5.4",
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
    _write_jsonl(
        logs_dir / "audit" / "intraday_rankings.jsonl",
        [
            {
                "timestamp": f"{run_date}T09:31:00",
                "run_date": run_date,
                "symbol": "NVDA",
                "trade_readiness_score": 72.5,
                "price_setup_score": 70.0,
                "candidate_score": 66.1,
                "technical_score": 70.0,
                "research_score": 60.0,
                "catalyst_score": 55.0,
                "liquidity_score": 80.0,
            }
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
        "intraday_rankings": 1,
        "factor_alpha": 0,
        "regime_state": 0,
        "portfolio_target": 0,
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


def test_build_analytics_db_loads_intraday_ranking_scores(tmp_path: Path) -> None:
    _make_sample_run(tmp_path, "2026-06-15")

    build_analytics_db(tmp_path)

    db_path = tmp_path / "runtime" / "analytics" / "analytics.db"
    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute(
            "SELECT symbol, trade_readiness_score, price_setup_score FROM intraday_rankings"
        ).fetchall()
    finally:
        connection.close()

    assert rows == [("NVDA", 72.5, 70.0)]


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
        "intraday_rankings": 0,
        "factor_alpha": 0,
        "regime_state": 0,
        "portfolio_target": 0,
    }


# --- N1: new columns + new advisory tables ---

def _seed_advisory_artifacts(agent_root: Path, run_date: str) -> None:
    """Add the H2 factor / K1 portfolio / K2 regime advisory artifacts to a run."""
    run_dir = agent_root / "runtime" / "state" / "runs" / run_date
    _write_json(run_dir / "planner" / "factor_alpha.json", {
        "date": run_date,
        "symbols": {
            "NVDA": {"factor_alpha_score": 82.0, "risk_flags": ["high_vol"],
                     "factor_components": {"momentum_12_1": 90.0}},
        },
    })
    _write_json(run_dir / "planner" / "regime_state.json", {
        "date": run_date, "regime": "risk_off", "multiplier": 0.5, "applied_multiplier": 0.5,
        "reasons": ["vix>=25 (28)"],
        "indicators": {"vix": 28.0, "spy_return_20d": -0.04, "spy_above_sma200": False},
    })
    _write_json(run_dir / "planner" / "portfolio_target.json", {
        "date": run_date, "total_equity": 100000.0, "cash": 20000.0, "cash_weight": 0.2,
        "theme_exposure": {"ai_semiconductor": 0.6}, "sector_exposure": {"technology": 0.6},
        "breaches": {"overexposed_themes": ["ai_semiconductor"]},
    })


def test_orders_table_captures_e4_and_setup_fields(tmp_path: Path) -> None:
    run_date = "2026-06-15"
    _make_sample_run(tmp_path, run_date)
    # Overwrite the order with the E4 + setup-level fields the real broker persists.
    _write_jsonl(
        tmp_path / "runtime" / "state" / "runs" / run_date / "paper" / "orders.jsonl",
        [{
            "order_id": "paper-nvda-1", "symbol": "NVDA", "side": "buy", "quantity": 1,
            "limit_price": 100.0, "notional": 100.0, "status": "filled", "fill_price": 100.2,
            "reason_codes": ["breakout"], "timestamp": f"{run_date}T09:31:05",
            "setup_type": "breakout", "stop_price": 95.0, "target_1": 110.0, "target_2": 120.0,
            "reward_risk": 2.0, "confidence": 0.8,
            "bid": 99.9, "ask": 100.1, "mid_price": 100.0, "spread_bps": 20.0, "slippage_bps": 12.0,
        }],
    )
    build_analytics_db(tmp_path)
    db_path = tmp_path / "runtime" / "analytics" / "analytics.db"
    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute(
            "SELECT spread_bps, slippage_bps, setup_type, reward_risk, mid_price FROM orders"
        ).fetchone()
    finally:
        connection.close()
    assert row == (20.0, 12.0, "breakout", 2.0, 100.0)


def test_decisions_table_captures_overlay_and_thesis(tmp_path: Path) -> None:
    run_date = "2026-06-15"
    _make_sample_run(tmp_path, run_date)
    _write_jsonl(
        tmp_path / "runtime" / "logs" / "runs" / run_date / "audit" / "decisions.jsonl",
        [{
            "timestamp": f"{run_date}T09:31:00", "decision": "would_trade",
            "proposed_order": {"symbol": "NVDA", "side": "buy", "setup_type": "breakout",
                               "confidence": 0.8, "thesis_tags": ["AI_INFRA", "MOMENTUM"]},
            "blocked_reasons": [],
            "per_candidate_blocks": {"PLTR": ["outside_entry_zone"]},
            "advisory_overlay": {"rank_delta": 3.0, "size_multiplier": 1.0},
        }],
    )
    build_analytics_db(tmp_path)
    db_path = tmp_path / "runtime" / "analytics" / "analytics.db"
    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute(
            "SELECT thesis_tags, per_candidate_blocks, advisory_overlay FROM decisions WHERE symbol='NVDA'"
        ).fetchone()
    finally:
        connection.close()
    assert json.loads(row[0]) == ["AI_INFRA", "MOMENTUM"]
    assert json.loads(row[1]) == {"PLTR": ["outside_entry_zone"]}
    assert json.loads(row[2])["rank_delta"] == 3.0


def test_new_advisory_tables_populate(tmp_path: Path) -> None:
    run_date = "2026-06-15"
    _make_sample_run(tmp_path, run_date)
    _seed_advisory_artifacts(tmp_path, run_date)
    counts = build_analytics_db(tmp_path)
    assert counts["factor_alpha"] == 1
    assert counts["regime_state"] == 1
    assert counts["portfolio_target"] == 1

    db_path = tmp_path / "runtime" / "analytics" / "analytics.db"
    connection = sqlite3.connect(db_path)
    try:
        fa = connection.execute("SELECT symbol, factor_alpha_score FROM factor_alpha").fetchone()
        regime = connection.execute("SELECT regime, vix, applied_multiplier, spy_above_sma200 FROM regime_state").fetchone()
        pt = connection.execute("SELECT total_equity, cash_weight, sector_exposure FROM portfolio_target").fetchone()
    finally:
        connection.close()
    assert fa == ("NVDA", 82.0)
    assert regime == ("risk_off", 28.0, 0.5, 0)  # spy_above_sma200 False -> 0
    assert pt[0] == 100000.0 and pt[1] == 0.2
    assert json.loads(pt[2]) == {"technology": 0.6}


def test_indexes_created(tmp_path: Path) -> None:
    _make_sample_run(tmp_path, "2026-06-15")
    build_analytics_db(tmp_path)
    db_path = tmp_path / "runtime" / "analytics" / "analytics.db"
    connection = sqlite3.connect(db_path)
    try:
        index_names = {r[0] for r in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
        ).fetchall()}
    finally:
        connection.close()
    assert "idx_candidates_run_date" in index_names
    assert "idx_orders_run_date_status" in index_names
    assert "idx_factor_alpha_run_date_symbol" in index_names
