import json
from pathlib import Path

from trading_agent.core.context import build_experiment_paths
from trading_agent.growth.evaluator import (
    evaluate_experiments,
    shadow_metrics,
    write_experiment_report,
)


def _seed_experiment(agent_root: Path) -> None:
    config_dir = agent_root / "src" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "strategy_experiments.yaml").write_text(
        "experiments:\n"
        "  exp_2026-06-15_scoring_trade_threshold:\n"
        "    status: active_shadow\n"
        "    challenger_strategy_id: \"baseline_v1__trade_threshold_40\"\n"
        "    parent_strategy_id: baseline_v1\n"
        "    module: scoring\n"
        "    field: trade_threshold\n"
        "    proposed: 40.0\n",
        encoding="utf-8",
    )
    (config_dir / "growth_policy.json").write_text(
        (Path.cwd() / "src" / "config" / "growth_policy.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )


def _seed_shadow_decisions(agent_root: Path, strategy_id: str, run_date: str, decisions: list[dict]) -> None:
    paths = build_experiment_paths(agent_root, run_date=run_date, strategy_id=strategy_id)
    paths.shadow_decisions_log_path.parent.mkdir(parents=True, exist_ok=True)
    with paths.shadow_decisions_log_path.open("w", encoding="utf-8") as fh:
        for row in decisions:
            fh.write(json.dumps({"run_date": run_date, **row}) + "\n")
    (agent_root / "runtime" / "state" / "runs" / run_date).mkdir(parents=True, exist_ok=True)


def test_shadow_metrics_counts_would_trade_and_no_trade():
    metrics = shadow_metrics([
        {"run_date": "2026-06-15", "decision": "would_trade", "blocked_reasons": []},
        {"run_date": "2026-06-15", "decision": "no_action", "blocked_reasons": ["below_trade_threshold"]},
        {"run_date": "2026-06-16", "decision": "no_action", "blocked_reasons": ["below_trade_threshold"]},
    ])
    assert metrics["total_evaluations"] == 3
    assert metrics["would_trade"] == 1
    assert metrics["no_trade_rate_pct"] == round(2 / 3 * 100, 1)
    assert metrics["shadow_days"] == 2
    assert metrics["reason_counts"]["below_trade_threshold"] == 2


def test_evaluate_experiments_reports_challenger_and_withholds_promotion(tmp_path):
    _seed_experiment(tmp_path)
    _seed_shadow_decisions(tmp_path, "baseline_v1__trade_threshold_40", "2026-06-15", [
        {"decision": "would_trade", "blocked_reasons": []},
    ])

    report = evaluate_experiments(tmp_path)

    assert "champion" in report
    challengers = report["challengers"]
    assert len(challengers) == 1
    chal = challengers[0]
    assert chal["challenger_strategy_id"] == "baseline_v1__trade_threshold_40"
    # Only 1 shadow day < min_shadow_days(10) and fill/drawdown unavailable => no promote.
    assert chal["recommendation"]["recommend_promote"] is False
    assert any("min_shadow_days" in r for r in chal["recommendation"]["blocking_reasons"])


def test_recommendation_positive_path_when_rules_relaxed(tmp_path):
    _seed_experiment(tmp_path)
    # Relax the policy: no fill/drawdown requirement, min_shadow_days=1.
    (tmp_path / "src" / "config" / "growth_policy.json").write_text(json.dumps({
        "mode": "paper_only",
        "promotion_rules": {
            "min_shadow_days": 1,
            "fill_rate_not_worse_than_champion": False,
            "max_drawdown_not_worse_than_champion": False,
            "require_human_final_approval": True,
        },
    }), encoding="utf-8")
    _seed_shadow_decisions(tmp_path, "baseline_v1__trade_threshold_40", "2026-06-15", [
        {"decision": "would_trade", "blocked_reasons": []},
    ])

    report = evaluate_experiments(tmp_path)
    rec = report["challengers"][0]["recommendation"]
    assert rec["recommend_promote"] is True
    # Even when recommended, a human must still approve — never auto.
    assert rec["requires_human_final_approval"] is True


def test_write_experiment_report_emits_json_and_md(tmp_path):
    _seed_experiment(tmp_path)
    _seed_shadow_decisions(tmp_path, "baseline_v1__trade_threshold_40", "2026-06-15", [
        {"decision": "no_action", "blocked_reasons": ["below_trade_threshold"]},
    ])

    json_path, md_path = write_experiment_report(tmp_path)

    assert json_path.exists() and md_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert "challengers" in payload
    assert "Promotion Recommendation" in md_path.read_text(encoding="utf-8")


def test_evaluator_reports_real_challenger_ledger_metrics(tmp_path):
    # G9: challenger has its own paper ledger -> evaluator surfaces real fill rate / drawdown / PnL.
    _seed_experiment(tmp_path)
    _seed_shadow_decisions(tmp_path, "baseline_v1__trade_threshold_40", "2026-06-15", [
        {"decision": "would_trade", "blocked_reasons": []},
    ])
    from trading_agent.core.context import build_experiment_runtime_paths
    exp = build_experiment_runtime_paths(tmp_path, run_date="2026-06-15", strategy_id="baseline_v1__trade_threshold_40")
    exp.paper_orders_log_path.parent.mkdir(parents=True, exist_ok=True)
    exp.paper_orders_log_path.write_text(json.dumps(
        {"order_id": "o1", "symbol": "NVDA", "side": "buy", "status": "filled", "fill_price": 100.0,
         "quantity": 1, "notional": 100.0, "timestamp": "2026-06-15T09:31:00"}) + "\n", encoding="utf-8")
    exp.paper_equity_curve_path.write_text(
        json.dumps({"timestamp": "2026-06-15T06:30:00", "total_equity": 1000.0, "realized_pnl": 0.0}) + "\n" +
        json.dumps({"timestamp": "2026-06-15T10:00:00", "total_equity": 950.0, "realized_pnl": -5.0}) + "\n" +
        json.dumps({"timestamp": "2026-06-15T13:00:00", "total_equity": 980.0, "realized_pnl": -2.0}) + "\n",
        encoding="utf-8")

    report = evaluate_experiments(tmp_path)
    m = report["challengers"][0]["metrics"]
    assert m["fill_rate_pct"] == 100.0       # 1 filled / 1 order
    assert m["realized_pnl"] == -2.0         # last equity-curve realized pnl
    assert m["max_drawdown"] == 0.05         # 1000 -> 950 = 5% peak-to-trough
