import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from trading_agent.orchestration import intraday as intraday_module
from trading_agent.policy.models import PolicyInputs, Quote


def policy_ready_inputs(*, trading_mode: str = "paper") -> PolicyInputs:
    return PolicyInputs(
        run_date="2026-06-14",
        trading_mode=trading_mode,
        risk_tier=0,
        risk_caps={"max_single_order_notional": 10, "max_daily_notional": 25},
        universe=["NVDA"],
        today_allowlist=["NVDA"],
        daily_plan={
            "date": "2026-06-14",
            "market_regime": "normal",
            "allowed_actions": ["small_limit_buy"],
            "today_watchlist": ["NVDA"],
            "symbol_trade_rules": {"NVDA": {"max_notional": 10}},
        },
        dynamic_allowlist={"date": "2026-06-14", "symbol_scores": {"NVDA": {"score": 85}}},
        daily_usage={"date": "2026-06-14", "used_notional": 0},
        account={"buying_power": 25.0},
        quotes={"NVDA": Quote(symbol="NVDA", price=100.0, previous_close=101.0, timestamp="2026-06-14T09:45:00-07:00")},
    )


def read_decisions(root: Path) -> list[dict[str, object]]:
    path = root / "runtime" / "logs" / "runs" / "2026-06-14" / "audit" / "decisions.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class IntradayPolicyIntegrationTests(unittest.TestCase):
    def test_intraday_uses_policy_and_does_not_call_codex_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            original_cwd = os.getcwd()
            os.chdir(root)
            try:
                with mock.patch.object(intraday_module, "_is_weekday_pt", return_value=True), \
                    mock.patch.object(intraday_module, "_is_intraday_window_pt", return_value=True), \
                    mock.patch.object(intraday_module, "pt_date_string", return_value="2026-06-14"), \
                    mock.patch.object(intraday_module, "load_runtime_config") as load_runtime_config, \
                    mock.patch.object(intraday_module, "load_policy_inputs", return_value=policy_ready_inputs()), \
                    mock.patch.object(intraday_module, "run_codex_prompt") as run_codex_prompt, \
                    mock.patch.object(intraday_module, "send_trade_email_notification") as notify:
                    load_runtime_config.return_value = mock.Mock(trading_mode="paper", risk_tier=0)

                    status = intraday_module.run_intraday_pipeline(dry_run=False)
                    decisions = read_decisions(root)
                    paper_dir = root / "runtime" / "state" / "runs" / "2026-06-14" / "paper"
                    paper_orders_written = (paper_dir / "orders.jsonl").exists()
                    day_start_written = (paper_dir / "day_start.json").exists()
                    equity_curve_written = (paper_dir / "equity_curve.jsonl").exists()
            finally:
                os.chdir(original_cwd)

        self.assertEqual(status, 0)
        run_codex_prompt.assert_not_called()
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0]["decision"], "would_trade")
        self.assertEqual(decisions[0]["action_taken"], "paper_fill")
        self.assertEqual(decisions[0]["proposed_order"]["symbol"], "NVDA")
        self.assertTrue(paper_orders_written)
        self.assertTrue(day_start_written)
        self.assertTrue(equity_curve_written)
        notify.assert_called_once()
        self.assertEqual(notify.call_args.kwargs["event_tag"], "TRADE_EXECUTED")

    def test_review_mode_blocks_when_execution_is_unwired(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            original_cwd = os.getcwd()
            os.chdir(root)
            try:
                with mock.patch.object(intraday_module, "_is_weekday_pt", return_value=True), \
                    mock.patch.object(intraday_module, "_is_intraday_window_pt", return_value=True), \
                    mock.patch.object(intraday_module, "pt_date_string", return_value="2026-06-14"), \
                    mock.patch.object(intraday_module, "load_runtime_config") as load_runtime_config, \
                    mock.patch.object(intraday_module, "load_policy_inputs", return_value=policy_ready_inputs(trading_mode="review")):
                    load_runtime_config.return_value = mock.Mock(trading_mode="review", risk_tier=0)

                    status = intraday_module.run_intraday_pipeline(dry_run=False)
                    decisions = read_decisions(root)
            finally:
                os.chdir(original_cwd)

        self.assertEqual(status, 0)
        self.assertEqual(decisions[0]["decision"], "blocked")
        self.assertIn("execution_not_wired", decisions[0]["blocked_reasons"])
        self.assertEqual(decisions[0]["action_taken"], "none")

    def test_existing_kill_switch_skip_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "KILL_SWITCH").write_text("", encoding="utf-8")
            original_cwd = os.getcwd()
            os.chdir(root)
            try:
                with mock.patch.object(intraday_module, "_is_weekday_pt", return_value=True), \
                    mock.patch.object(intraday_module, "_is_intraday_window_pt", return_value=True), \
                    mock.patch.object(intraday_module, "pt_date_string", return_value="2026-06-14"):
                    status = intraday_module.run_intraday_pipeline(dry_run=False)
                    decisions = read_decisions(root)
            finally:
                os.chdir(original_cwd)

        self.assertEqual(status, 0)
        self.assertEqual(decisions[0]["decision"], "kill_switch_skip")


if __name__ == "__main__":
    unittest.main()
