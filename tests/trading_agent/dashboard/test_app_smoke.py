"""Headless render smoke test for the dashboard.

Skipped automatically when streamlit isn't installed (it's an optional `dashboard`
extra), so the normal test suite is unaffected. When streamlit IS present this actually
executes app.py via streamlit's AppTest harness — catching cross-reference / runtime
errors across all tabs without needing a browser or screenshot.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest  # noqa: E402

from trading_agent.analytics.build_db import build_analytics_db  # noqa: E402
from trading_agent.core.io import write_json  # noqa: E402

APP_PATH = Path(__file__).resolve().parents[3] / "src" / "trading_agent" / "dashboard" / "app.py"


def _seed(root: Path) -> None:
    rd = "2026-06-15"
    run = root / "runtime" / "state" / "runs" / rd
    logs = root / "runtime" / "logs" / "runs" / rd / "audit"
    logs.mkdir(parents=True, exist_ok=True)
    write_json(run / "run_manifest.json", {"run_date": rd, "strategy_id": "baseline_v1", "trading_mode": "paper", "effective_risk_tier": 4})
    write_json(run / "planner" / "daily_plan.json", {"plan_state": "trade_ready", "market_regime": "aggressive_ok"})
    write_json(run / "planner" / "risk_overlay.json", {"market_regime": "aggressive_ok", "watchlist_candidates": ["NVDA"], "tradable_candidates": ["NVDA"]})
    write_json(run / "planner" / "candidate_scores.json", {"symbols": {"NVDA": {"score": 66.0, "score_status": "scored", "components": {"technical": 70.0, "catalyst": 55.0, "dsa": 60.0, "kronos": 65.0, "quote": 50.0}}}})
    write_json(run / "planner" / "premarket_diagnostics.json", {"theme_diagnostics": {"watchlist": {"dominant_theme": "ai_semiconductor", "max_theme_pct": 70.0, "theme_distribution": {"ai_semiconductor": {"pct": 70.0}}}}})
    (logs / "decisions.jsonl").write_text(json.dumps({"timestamp": f"{rd}T09:31:00", "decision": "would_trade", "proposed_order": {"symbol": "NVDA", "side": "buy", "setup_type": "breakout", "confidence": 0.8}, "blocked_reasons": []}) + "\n", encoding="utf-8")
    (logs / "intraday_rankings.jsonl").write_text(json.dumps({"timestamp": f"{rd}T09:31:00", "run_date": rd, "symbol": "NVDA", "trade_readiness_score": 72.5, "price_setup_score": 70.0, "candidate_score": 66.0, "technical_score": 70.0, "research_score": 60.0, "catalyst_score": 55.0, "liquidity_score": 80.0}) + "\n", encoding="utf-8")
    paper = run / "paper"
    paper.mkdir(parents=True, exist_ok=True)
    (paper / "orders.jsonl").write_text(json.dumps({"order_id": "o1", "symbol": "NVDA", "side": "buy", "quantity": 1, "limit_price": 100.0, "notional": 100.0, "status": "filled", "fill_price": 100.0, "reason_codes": ["breakout"], "timestamp": f"{rd}T09:31:05"}) + "\n", encoding="utf-8")
    (paper / "equity_curve.jsonl").write_text(json.dumps({"timestamp": f"{rd}T13:00:00", "date": rd, "event": "day_end", "cash": 900.0, "positions_market_value": 100.0, "total_equity": 1005.0, "realized_pnl": 5.0}) + "\n", encoding="utf-8")
    write_json(root / "runtime" / "analytics" / "experiment_report.json", {"champion": {"fill_rate_pct": 100.0, "no_trade_rate_pct": 0.0, "run_date_count": 1}, "challengers": [{"challenger_strategy_id": "c1", "status": "active_shadow", "metrics": {"shadow_days": 1, "total_evaluations": 1, "would_trade": 1, "no_trade_rate_pct": 0.0}, "recommendation": {"recommend_promote": False, "blocking_reasons": ["min_shadow_days_not_met: 1 < 10"]}}]})
    build_analytics_db(root)


def test_dashboard_renders_all_tabs_without_error(tmp_path, monkeypatch):
    _seed(tmp_path)
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_file(str(APP_PATH), default_timeout=60)
    app.run()
    assert not app.exception, app.exception
    assert len(app.tabs) == 7
    headers = [h.value for h in app.header]
    assert any("Strategy Comparison" in h for h in headers)
    assert any("Today" in h for h in headers)
