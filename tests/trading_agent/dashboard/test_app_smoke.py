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
    (logs / "intraday_rankings.jsonl").write_text(json.dumps({"timestamp": f"{rd}T09:31:00", "run_date": rd, "symbol": "NVDA", "base_trade_readiness_score": 70.5, "advisory_rank_delta": 2.0, "trade_readiness_score": 72.5, "price_setup_score": 70.0, "candidate_score": 66.0, "technical_score": 70.0, "research_score": 60.0, "catalyst_score": 55.0, "liquidity_score": 80.0, "advisory_overlay": {"rank_delta": 2.0, "size_multiplier": 1.0, "block_buy": False, "blocked_reasons": [], "components": {"factor_alpha": {"score": 82.0}, "ai": {"kronos": {"direction": "long", "confidence": 0.8}}, "regime": {"regime": "neutral"}, "portfolio": {"position_weight": 0.04}}}}) + "\n", encoding="utf-8")
    paper = run / "paper"
    paper.mkdir(parents=True, exist_ok=True)
    (paper / "orders.jsonl").write_text(
        json.dumps({"order_id": "o1", "symbol": "NVDA", "side": "buy", "quantity": 2, "limit_price": 100.0, "notional": 200.0, "status": "filled", "fill_price": 100.0, "reason_codes": ["breakout"], "setup_type": "breakout", "stop_price": 96.0, "target_1": 108.0, "target_2": 114.0, "reward_risk": 2.0, "confidence": 0.8, "slippage_bps": 4.0, "timestamp": f"{rd}T09:31:05"}) + "\n"
        + json.dumps({"order_id": "o2", "symbol": "NVDA", "side": "sell", "quantity": 2, "limit_price": 102.0, "notional": 204.0, "status": "filled", "fill_price": 102.0, "reason_codes": ["target_1"], "setup_type": "breakout", "timestamp": f"{rd}T12:31:05"}) + "\n",
        encoding="utf-8")
    (paper / "equity_curve.jsonl").write_text(json.dumps({"timestamp": f"{rd}T13:00:00", "date": rd, "event": "day_end", "cash": 900.0, "positions_market_value": 100.0, "total_equity": 1005.0, "realized_pnl": 5.0}) + "\n", encoding="utf-8")
    # K线复盘: daily OHLCV for NVDA/SPY + an isolated challenger ledger (different buy point).
    import datetime as _dt
    _bars = []
    _d0 = _dt.date(2026, 5, 1)
    for _i in range(40):
        _day = (_d0 + _dt.timedelta(days=_i)).isoformat()
        _base = 90.0 + _i * 0.4
        _bars.append({"timestamp": f"{_day}T00:00:00", "open": round(_base, 2), "high": round(_base + 2, 2),
                      "low": round(_base - 2, 2), "close": round(_base + 0.5, 2), "volume": 1_000_000 + _i * 5000})
    _bars.append({"timestamp": f"{rd}T00:00:00", "open": 99.0, "high": 103.0, "low": 98.0, "close": 102.0, "volume": 2_000_000})
    for _sym in ("NVDA", "SPY"):
        write_json(run / "market_feed" / "ohlcv" / _sym / "daily.json", _bars)
    chal = run / "experiments" / "challenger_v1" / "paper"
    chal.mkdir(parents=True, exist_ok=True)
    (chal / "orders.jsonl").write_text(json.dumps({"order_id": "c1o1", "symbol": "NVDA", "side": "buy", "quantity": 1, "limit_price": 96.0, "notional": 96.0, "status": "filled", "fill_price": 96.0, "reason_codes": ["pullback"], "setup_type": "pullback", "stop_price": 92.0, "target_1": 106.0, "reward_risk": 2.5, "confidence": 0.7, "slippage_bps": 3.0, "timestamp": f"{rd}T09:35:00"}) + "\n", encoding="utf-8")
    write_json(root / "runtime" / "analytics" / "experiment_report.json", {"champion": {"fill_rate_pct": 100.0, "no_trade_rate_pct": 0.0, "run_date_count": 1}, "challengers": [{"challenger_strategy_id": "c1", "status": "active_shadow", "metrics": {"shadow_days": 1, "total_evaluations": 1, "would_trade": 1, "no_trade_rate_pct": 0.0}, "recommendation": {"recommend_promote": False, "blocking_reasons": ["min_shadow_days_not_met: 1 < 10"]}}]})
    write_json(root / "runtime" / "analytics" / "calibration_report.json", {
        "generated_at": "x", "run_date_count": 1, "sample_size": 1, "horizons": [1],
        "score_buckets": {"candidate_score": {"1": [{"bucket": 1, "count": 1, "score_min": 66.0, "score_max": 66.0, "mean_return": 0.01, "hit_rate": 1.0}]},
                          "trade_readiness_score": {"1": []}, "price_setup_score": {"1": []}},
        "attribution": {"1": [{"component": "technical", "n": 1, "ic": None}]},
        "ic_summary": [{"component": "technical", "horizons": {"1": {"periods": 1, "mean_ic": 0.1, "std_ic": None, "t_stat": None, "pooled_ic": 0.1}}}],
        "benchmarks": {"SPY": {"1": {"count": 1, "mean_return": 0.002}}},
        "setup_outcomes": [{"setup_type": "breakout", "fills": 1, "target_first": 1, "stop_first": 0, "undecided": 0, "win_rate": 1.0}]})
    write_json(run / "planner" / "factor_alpha.json", {"date": rd, "profile": "baseline_price_factors_v1", "symbols": {"NVDA": {"factor_alpha_score": 78.5, "coverage": 1.0, "risk_flags": [], "factor_components": {"momentum_12_1": 80.0}}}})
    write_json(root / "runtime" / "analytics" / "fill_quality_report.json", {
        "generated_at": "x", "fill_count": 2, "total_filled_notional": 2000.0,
        "mean_realized_slippage_bps": 10.0, "mean_realized_slippage_buy_bps": 10.0, "mean_realized_slippage_sell_bps": 10.0,
        "bucket_basis": "realized_slippage_proxy",
        "buckets": [{"bucket": "normal (5-15bps)", "count": 2, "mean_slippage_bps": 10.0}],
        "scenarios": [{"assumed_spread_bps": 10.0, "per_side_cost_bps": 5.0, "extra_vs_realized_per_side_bps": 0.0, "roundtrip_edge_haircut_bps": 10.0, "dollar_drag_on_filled_notional": 2.0}]})
    write_json(root / "runtime" / "analytics" / "ai_signal_study.json", {
        "generated_at": "x", "horizons": [1], "primary_horizon": 1, "ai_signal_count": 1, "matched_count": 1,
        "layers": {"kronos": {"signal_count": 1, "confidence_calibration": {"1": [{"bucket": 1, "count": 1, "confidence_min": 0.8, "confidence_max": 0.8, "mean_return": 0.05, "hit_rate": 1.0}]},
                              "confidence_ic": {"1": None}, "directional_accuracy": 1.0, "directional_count": 1,
                              "reason_code_lift": [{"code": "setup:breakout", "count": 1, "mean_return_with": 0.05, "lift_vs_baseline": 0.0}], "warning_code_lift": []},
                   "dsa": {"signal_count": 0}, "catalyst": {"signal_count": 0}}})
    write_json(root / "runtime" / "analytics" / "ai_ablation.json", {
        "generated_at": "x", "primary_horizon": 1, "ai_signal_count": 2, "matched_symbol_runs": 2,
        "variants": {"full_ai": {"ic": 0.9, "n": 2}, "drop_kronos": {"ic": None, "n": 2, "marginal_ic_of_layer": None},
                     "drop_dsa": {"ic": 0.9, "n": 2, "marginal_ic_of_layer": 0.0}, "factor_only": {"ic": None, "n": 0},
                     "ai_plus_factor": {"ic": None, "n": 0}}})
    hist = root / "runtime" / "analytics" / "history" / rd
    hist.mkdir(parents=True, exist_ok=True)
    write_json(hist / "nightly_summary.json", {
        "date": rd, "generated_at": "x", "fill_rate_pct": 100.0, "no_trade_rate_pct": 0.0,
        "calibration_sample_size": 1, "proposal_count": 1, "active_shadow_count": 0,
        "top_component_ic": {"1": {"component": "technical", "ic": 0.1}}, "champion": {"fill_rate_pct": 100.0}, "challengers": []})
    write_json(root / "runtime" / "analytics" / "nightly_health.json", {
        "generated_at": "x", "status": "ok", "last_nightly_run_date": rd, "failed_steps": [],
        "stale_reports": [], "reports": []})
    write_json(run / "planner" / "portfolio_target.json", {
        "date": rd, "total_equity": 100000.0, "cash": 20000.0, "cash_weight": 0.2,
        "targets": {"cash_target": 0.2, "max_position_size": 0.08, "theme_cap": 0.35},
        "position_weights": {"NVDA": 0.4}, "theme_exposure": {"ai_semiconductor": 0.4},
        "breaches": {"below_cash_target": False, "oversize_positions": ["NVDA"], "overexposed_themes": ["ai_semiconductor"]},
        "notes": "Advisory only."})
    write_json(run / "planner" / "regime_state.json", {
        "date": rd, "regime": "neutral", "multiplier": 1.0, "applied_multiplier": 1.0,
        "reasons": ["no risk-off / bull trigger"], "indicators": {}})
    build_analytics_db(root)


def test_dashboard_renders_all_tabs_without_error(tmp_path, monkeypatch):
    _seed(tmp_path)
    monkeypatch.setenv("AGENT_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_file(str(APP_PATH), default_timeout=60)
    app.run()
    assert not app.exception, app.exception
    assert len(app.tabs) == 6
    headers = [h.value for h in app.header]
    assert any("今日驾驶舱" in h for h in headers)
    assert any("选股与决策" in h for h in headers)
    assert any("业绩与对比" in h for h in headers)
    assert any("K线复盘" in h for h in headers)
    assert any("校准与归因" in h for h in headers)
    assert any("成长与趋势" in h for h in headers)


def test_dashboard_ignores_current_working_directory(tmp_path, monkeypatch):
    _seed(tmp_path)
    (tmp_path / "src").mkdir()
    monkeypatch.setenv("AGENT_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path / "src")
    app = AppTest.from_file(str(APP_PATH), default_timeout=60)
    app.run()
    assert not app.exception, app.exception
    assert len(app.tabs) == 6
