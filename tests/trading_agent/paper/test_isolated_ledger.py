from __future__ import annotations

from datetime import datetime
from pathlib import Path

from trading_agent.core.context import build_experiment_runtime_paths, build_runtime_paths
from trading_agent.core.time import PT
from trading_agent.paper.broker import apply_paper_intent, record_paper_day_start
from trading_agent.policy.models import OrderIntent, PolicyDecision


def _decision() -> PolicyDecision:
    intent = OrderIntent(symbol="NVDA", side="buy", order_type="limit", limit_price=100.0,
                         estimated_notional=100.0, quantity=1.0, reference_price=99.0, setup_type="breakout",
                         stop_price=95.0, target_1=110.0, reward_risk=2.0, confidence=0.8)
    return PolicyDecision(trading_mode="paper", checked_symbols=["NVDA"], decision="would_trade",
                          intent=intent, blocked_reasons=[])


def test_experiment_runtime_paths_are_isolated():
    exp = build_experiment_runtime_paths(Path("/agent"), run_date="2026-06-15", strategy_id="chal_x")
    champ = build_runtime_paths(Path("/agent"), run_date="2026-06-15")
    assert "experiments/chal_x/paper" in str(exp.paper_orders_log_path)
    assert exp.paper_orders_log_path != champ.paper_orders_log_path
    assert exp.daily_usage_path != champ.daily_usage_path


def test_paper_fill_writes_isolated_ledger_only(tmp_path, monkeypatch):
    monkeypatch.setattr("trading_agent.paper.broker.datetime", _FixedDatetime)
    exp = build_experiment_runtime_paths(tmp_path, run_date="2026-06-15", strategy_id="chal_x")
    record_paper_day_start(tmp_path, run_date="2026-06-15", starting_cash=1000.0, paths_override=exp)

    result = apply_paper_intent(tmp_path, run_date="2026-06-15", decision=_decision(), starting_cash=1000.0, paths_override=exp)

    assert result.applied
    # Challenger ledger written under experiments/.
    assert exp.paper_orders_log_path.exists()
    assert exp.paper_account_path.exists()
    # Champion ledger untouched.
    champ = build_runtime_paths(tmp_path, run_date="2026-06-15")
    assert not champ.paper_orders_log_path.exists()
    assert not champ.paper_account_path.exists()


class _FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):  # noqa: D401 - deterministic timestamp for the order id
        return datetime(2026, 6, 15, 9, 31, 0, tzinfo=PT)
