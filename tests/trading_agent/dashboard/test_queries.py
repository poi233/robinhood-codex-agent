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


def test_growth_observations_missing_returns_empty(tmp_path):
    from trading_agent.dashboard.queries import growth_observations

    assert growth_observations(tmp_path) == {}


def test_growth_observations_reads_artifact(tmp_path):
    import json
    from trading_agent.dashboard.queries import growth_observations

    out = tmp_path / "runtime" / "analytics"
    out.mkdir(parents=True)
    (out / "growth_observations.json").write_text(
        json.dumps({"global": [{"type": "high_no_trade_rate"}], "modules": {}}), encoding="utf-8"
    )
    payload = growth_observations(tmp_path)
    assert payload["global"][0]["type"] == "high_no_trade_rate"


# --- C3 Dashboard v2 query tests ---

def _seed_run_files(agent_root: Path, run_date: str, *, strategy_id: str, score: float,
                    decision: str, order_status: str, realized_pnl: float) -> None:
    """Write one run's source files (no DB build) with intraday rankings + theme diagnostics."""
    run_dir = agent_root / "runtime" / "state" / "runs" / run_date
    paper_dir = run_dir / "paper"
    logs_dir = agent_root / "runtime" / "logs" / "runs" / run_date / "audit"
    write_json(run_dir / "run_manifest.json", {"run_date": run_date, "strategy_id": strategy_id,
                                               "trading_mode": "paper", "effective_risk_tier": 4})
    write_json(run_dir / "planner" / "candidate_scores.json", {"symbols": {
        "NVDA": {"score": score, "score_status": "scored",
                 "components": {"technical": score, "catalyst": 50.0, "dsa": 60.0, "kronos": 55.0, "quote": 50.0}}}})
    write_json(run_dir / "planner" / "risk_overlay.json",
               {"watchlist_candidates": ["NVDA"], "tradable_candidates": ["NVDA"]})
    write_json(run_dir / "planner" / "premarket_diagnostics.json",
               {"theme_diagnostics": {"watchlist": {"dominant_theme": "ai_semiconductor", "max_theme_pct": 70.0}}})
    _write_jsonl(logs_dir / "decisions.jsonl", [
        {"timestamp": f"{run_date}T09:31:00", "decision": decision,
         "proposed_order": {"symbol": "NVDA", "side": "buy", "setup_type": "breakout", "confidence": 0.8},
         "blocked_reasons": [] if decision == "would_trade" else ["below_trade_threshold"]}])
    _write_jsonl(logs_dir / "intraday_rankings.jsonl", [
        {"timestamp": f"{run_date}T09:31:00", "run_date": run_date, "symbol": "NVDA",
         "trade_readiness_score": 72.5, "price_setup_score": 70.0, "candidate_score": score,
         "technical_score": score, "research_score": 60.0, "catalyst_score": 50.0, "liquidity_score": 80.0}])
    _write_jsonl(paper_dir / "orders.jsonl", [
        {"order_id": f"paper-{run_date}", "symbol": "NVDA", "side": "buy", "quantity": 1, "limit_price": 100.0,
         "notional": 100.0, "status": order_status, "fill_price": 100.0 if order_status == "filled" else None,
         "reason_codes": ["breakout"], "timestamp": f"{run_date}T09:31:05"}])
    _write_jsonl(paper_dir / "equity_curve.jsonl", [
        {"timestamp": f"{run_date}T13:00:00", "date": run_date, "event": "day_end", "cash": 900.0,
         "positions_market_value": 100.0, "total_equity": 1000.0 + realized_pnl, "realized_pnl": realized_pnl}])


def test_candidates_with_rankings_joins_intraday_scores(tmp_path: Path) -> None:
    _seed_run_files(tmp_path, "2026-06-15", strategy_id="baseline_v1", score=66.0,
                    decision="would_trade", order_status="filled", realized_pnl=5.0)
    build_analytics_db(tmp_path)
    rows = queries.candidates_with_rankings(tmp_path, "2026-06-15")
    assert rows and rows[0]["symbol"] == "NVDA"
    assert rows[0]["trade_readiness_score"] == 72.5
    assert rows[0]["price_setup_score"] == 70.0


def test_strategy_comparison_groups_by_strategy_id(tmp_path: Path) -> None:
    _seed_run_files(tmp_path, "2026-06-15", strategy_id="baseline_v1", score=66.0,
                    decision="would_trade", order_status="filled", realized_pnl=5.0)
    _seed_run_files(tmp_path, "2026-06-16", strategy_id="challenger_v2", score=40.0,
                    decision="no_trade", order_status="pending", realized_pnl=-2.0)
    build_analytics_db(tmp_path)
    rows = queries.strategy_comparison(tmp_path)
    assert {r["strategy_id"] for r in rows} == {"baseline_v1", "challenger_v2"}
    baseline = next(r for r in rows if r["strategy_id"] == "baseline_v1")
    challenger = next(r for r in rows if r["strategy_id"] == "challenger_v2")
    assert baseline["fill_rate_pct"] == 100.0
    assert baseline["no_trade_rate_pct"] == 0.0
    assert challenger["no_trade_rate_pct"] == 100.0
    assert baseline["total_realized_pnl"] == 5.0
    assert challenger["total_realized_pnl"] == -2.0


def test_strategy_comparison_empty_without_db(tmp_path: Path) -> None:
    assert queries.strategy_comparison(tmp_path) == []


def test_equity_timeseries_ordered_and_filtered(tmp_path: Path) -> None:
    _seed_run_files(tmp_path, "2026-06-15", strategy_id="baseline_v1", score=66.0,
                    decision="would_trade", order_status="filled", realized_pnl=5.0)
    _seed_run_files(tmp_path, "2026-06-16", strategy_id="baseline_v1", score=66.0,
                    decision="would_trade", order_status="filled", realized_pnl=3.0)
    build_analytics_db(tmp_path)
    series = queries.equity_timeseries(tmp_path)
    assert [row["run_date"] for row in series] == ["2026-06-15", "2026-06-16"]
    only_16 = queries.equity_timeseries(tmp_path, since="2026-06-16")
    assert [row["run_date"] for row in only_16] == ["2026-06-16"]


def test_blocked_reason_trend(tmp_path: Path) -> None:
    _seed_run_files(tmp_path, "2026-06-16", strategy_id="baseline_v1", score=40.0,
                    decision="no_trade", order_status="pending", realized_pnl=0.0)
    build_analytics_db(tmp_path)
    trend = queries.blocked_reason_trend(tmp_path)
    assert any(r["reason"] == "below_trade_threshold" for r in trend)


def test_champion_vs_challengers_reads_report(tmp_path: Path) -> None:
    assert queries.champion_vs_challengers(tmp_path) == {}
    out = tmp_path / "runtime" / "analytics"
    out.mkdir(parents=True)
    (out / "experiment_report.json").write_text(json.dumps(
        {"champion": {"fill_rate_pct": 50.0}, "challengers": [{"challenger_strategy_id": "c1"}]}), encoding="utf-8")
    payload = queries.champion_vs_challengers(tmp_path)
    assert payload["challengers"][0]["challenger_strategy_id"] == "c1"


def test_proposals_and_queue_and_theme_overviews(tmp_path: Path) -> None:
    # proposals
    pdir = tmp_path / "runtime" / "strategy_proposals" / "2026-06-16"
    pdir.mkdir(parents=True)
    (pdir / "proposal_001_scoring_trade_threshold.json").write_text(json.dumps(
        {"proposal_id": "p1", "mutation": {"module": "scoring", "field": "trade_threshold"}, "status": "proposed"}),
        encoding="utf-8")
    assert queries.proposals_overview(tmp_path)[0]["proposal_id"] == "p1"
    # queue
    cfg = tmp_path / "src" / "config"
    cfg.mkdir(parents=True)
    (cfg / "strategy_experiments.yaml").write_text(
        "experiments:\n  exp_x:\n    status: active_shadow\n    challenger_strategy_id: \"c1\"\n", encoding="utf-8")
    assert queries.experiment_queue_overview(tmp_path)[0]["status"] == "active_shadow"
    # theme
    _seed_run_files(tmp_path, "2026-06-15", strategy_id="baseline_v1", score=66.0,
                    decision="would_trade", order_status="filled", realized_pnl=5.0)
    assert queries.theme_diagnostics(tmp_path, "2026-06-15")["watchlist"]["dominant_theme"] == "ai_semiconductor"


def test_calibration_report_missing_and_present(tmp_path):
    import json
    from trading_agent.dashboard.queries import calibration_report
    assert calibration_report(tmp_path) == {}
    out = tmp_path / "runtime" / "analytics"; out.mkdir(parents=True)
    (out / "calibration_report.json").write_text(json.dumps({"sample_size": 3, "horizons": [1, 3, 5]}), encoding="utf-8")
    assert calibration_report(tmp_path)["sample_size"] == 3


def test_factor_alpha_query(tmp_path):
    import json
    from trading_agent.core.context import build_runtime_paths
    from trading_agent.dashboard.queries import factor_alpha
    assert factor_alpha(tmp_path, "2026-06-15") == {}
    p = build_runtime_paths(tmp_path, run_date="2026-06-15").factor_alpha_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"profile": "p", "symbols": {"NVDA": {"factor_alpha_score": 80.0}}}), encoding="utf-8")
    assert factor_alpha(tmp_path, "2026-06-15")["symbols"]["NVDA"]["factor_alpha_score"] == 80.0


def test_fill_quality_report_query(tmp_path):
    import json
    from trading_agent.dashboard.queries import fill_quality_report
    assert fill_quality_report(tmp_path) == {}
    out = tmp_path / "runtime" / "analytics"; out.mkdir(parents=True, exist_ok=True)
    (out / "fill_quality_report.json").write_text(json.dumps({"fill_count": 5}), encoding="utf-8")
    assert fill_quality_report(tmp_path)["fill_count"] == 5


def test_ai_signal_study_query(tmp_path):
    import json
    from trading_agent.dashboard.queries import ai_signal_study
    assert ai_signal_study(tmp_path) == {}
    out = tmp_path / "runtime" / "analytics"; out.mkdir(parents=True, exist_ok=True)
    (out / "ai_signal_study.json").write_text(json.dumps({"matched_count": 3}), encoding="utf-8")
    assert ai_signal_study(tmp_path)["matched_count"] == 3


def test_ai_ablation_query(tmp_path):
    import json
    from trading_agent.dashboard.queries import ai_ablation
    assert ai_ablation(tmp_path) == {}
    out = tmp_path / "runtime" / "analytics"; out.mkdir(parents=True, exist_ok=True)
    (out / "ai_ablation.json").write_text(json.dumps({"matched_symbol_runs": 4}), encoding="utf-8")
    assert ai_ablation(tmp_path)["matched_symbol_runs"] == 4


def test_analysis_history_and_snapshot_queries(tmp_path):
    import json
    from trading_agent.dashboard.queries import analysis_history_dates, analysis_snapshot, analysis_trend
    assert analysis_history_dates(tmp_path) == []
    assert analysis_snapshot(tmp_path, "2026-06-17") == {}
    assert analysis_trend(tmp_path)["status"] == "insufficient_data"
    for d in ("2026-06-16", "2026-06-17"):
        hist = tmp_path / "runtime" / "analytics" / "history" / d
        hist.mkdir(parents=True)
        (hist / "nightly_summary.json").write_text(json.dumps({"date": d, "fill_rate_pct": 100.0}), encoding="utf-8")
    assert analysis_history_dates(tmp_path) == ["2026-06-17", "2026-06-16"]  # newest first
    assert analysis_snapshot(tmp_path, "2026-06-17")["fill_rate_pct"] == 100.0
    assert analysis_trend(tmp_path)["status"] == "ok"


def test_nightly_health_query(tmp_path):
    import json
    from trading_agent.dashboard.queries import nightly_health
    assert nightly_health(tmp_path) == {}
    out = tmp_path / "runtime" / "analytics"; out.mkdir(parents=True, exist_ok=True)
    (out / "nightly_health.json").write_text(json.dumps({"status": "ok", "failed_steps": []}), encoding="utf-8")
    assert nightly_health(tmp_path)["status"] == "ok"


def test_portfolio_target_query(tmp_path):
    import json
    from trading_agent.core.context import build_runtime_paths
    from trading_agent.dashboard.queries import portfolio_target
    assert portfolio_target(tmp_path, "2026-06-17") == {}
    p = build_runtime_paths(tmp_path, run_date="2026-06-17").planner_dir / "portfolio_target.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"total_equity": 100000.0, "cash_weight": 0.2, "breaches": {}}), encoding="utf-8")
    assert portfolio_target(tmp_path, "2026-06-17")["total_equity"] == 100000.0


def test_regime_state_query(tmp_path):
    import json
    from trading_agent.core.context import build_runtime_paths
    from trading_agent.dashboard.queries import regime_state
    assert regime_state(tmp_path, "2026-06-17") == {}
    p = build_runtime_paths(tmp_path, run_date="2026-06-17").planner_dir / "regime_state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"regime": "bull", "applied_multiplier": 1.0, "reasons": []}), encoding="utf-8")
    assert regime_state(tmp_path, "2026-06-17")["regime"] == "bull"


def test_advisory_overlay_summary_reads_intraday_rankings(tmp_path: Path) -> None:
    from trading_agent.dashboard.queries import advisory_overlay_summary

    rows = advisory_overlay_summary(tmp_path, "2026-06-17")
    assert rows == []

    _write_jsonl(
        tmp_path / "runtime" / "logs" / "runs" / "2026-06-17" / "audit" / "intraday_rankings.jsonl",
        [
            {
                "timestamp": "2026-06-17T09:31:00",
                "run_date": "2026-06-17",
                "symbol": "NVDA",
                "base_trade_readiness_score": 80.0,
                "advisory_rank_delta": 5.0,
                "trade_readiness_score": 85.0,
                "advisory_overlay": {
                    "rank_delta": 5.0,
                    "size_multiplier": 0.5,
                    "block_buy": False,
                    "blocked_reasons": [],
                    "components": {
                        "factor_alpha": {"score": 88.0},
                        "ai": {"kronos": {"direction": "long", "confidence": 0.8}},
                    },
                },
            }
        ],
    )

    rows = advisory_overlay_summary(tmp_path, "2026-06-17")

    assert rows == [
        {
            "timestamp": "2026-06-17T09:31:00",
            "symbol": "NVDA",
            "base_trade_readiness_score": 80.0,
            "advisory_rank_delta": 5.0,
            "final_trade_readiness_score": 85.0,
            "size_multiplier": 0.5,
            "block_buy": False,
            "blocked_reasons": "",
            "factor_alpha_score": 88.0,
            "ai_layers": "kronos:long@0.8",
            "regime": "",
            "portfolio": "",
        }
    ]


def test_thesis_attribution_returns_report(tmp_path):
    import json
    from trading_agent.dashboard.queries import thesis_attribution

    out = tmp_path / "runtime" / "analytics"
    out.mkdir(parents=True)
    (out / "thesis_attribution.json").write_text(json.dumps({
        "generated_at": "2026-06-18T01:00:00+00:00",
        "primary_horizon": 5,
        "sample_size": 25,
        "min_count": 3,
        "theses": [
            {"thesis": "AI_INFRA", "count": 10, "win_rate": 0.70, "mean_return": 0.018},
            {"thesis": "MOMENTUM", "count": 8, "win_rate": 0.625, "mean_return": 0.012},
        ],
    }), encoding="utf-8")

    result = thesis_attribution(tmp_path)

    assert result["primary_horizon"] == 5
    assert len(result["theses"]) == 2
    assert result["theses"][0]["thesis"] == "AI_INFRA"


def test_thesis_attribution_missing_returns_empty(tmp_path):
    from trading_agent.dashboard.queries import thesis_attribution

    result = thesis_attribution(tmp_path)

    assert result == {}


def test_thesis_trend_builds_per_thesis_series(tmp_path):
    import json
    from trading_agent.dashboard.queries import thesis_trend

    hist = tmp_path / "runtime" / "analytics" / "history"
    for date, ai_win in (("2026-06-16", 0.60), ("2026-06-17", 0.65), ("2026-06-18", 0.70)):
        d = hist / date
        d.mkdir(parents=True)
        (d / "thesis_attribution.json").write_text(json.dumps({
            "theses": [
                {"thesis": "AI_INFRA", "win_rate": ai_win, "mean_return": 0.01, "count": 10},
            ]
        }), encoding="utf-8")

    series = thesis_trend(tmp_path)

    assert "AI_INFRA" in series
    assert len(series["AI_INFRA"]) == 3
    # ascending by date
    assert [p["date"] for p in series["AI_INFRA"]] == ["2026-06-16", "2026-06-17", "2026-06-18"]
    assert series["AI_INFRA"][-1]["win_rate"] == 0.70


def test_thesis_trend_empty_when_no_history(tmp_path):
    from trading_agent.dashboard.queries import thesis_trend

    assert thesis_trend(tmp_path) == {}
