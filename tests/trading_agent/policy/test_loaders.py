import json
import tempfile
import unittest
from pathlib import Path

from trading_agent.policy.loaders import load_policy_inputs


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class PolicyLoaderTests(unittest.TestCase):
    def test_load_policy_inputs_reads_local_config_and_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "src" / "config").mkdir(parents=True)
            (root / "runtime" / "state" / "runs" / "2026-06-14" / "planner").mkdir(parents=True)
            (root / "src" / "config" / "universe.txt").write_text("NVDA\n# comment\nSMH\n", encoding="utf-8")
            (root / "runtime" / "state" / "runs" / "2026-06-14" / "planner" / "today_allowlist.txt").write_text("NVDA\nSMH # broad ETF\n", encoding="utf-8")
            write_json(
                root / "src" / "config" / "risk_tiers.json",
                {"0": {"max_single_order_notional": 10, "max_daily_notional": 25}},
            )
            write_json(
                root / "runtime" / "state" / "runs" / "2026-06-14" / "planner" / "daily_plan.json",
                {
                    "date": "2026-06-14",
                    "market_regime": "normal",
                    "allowed_actions": ["small_limit_buy"],
                    "today_watchlist": ["NVDA"],
                    "symbol_trade_rules": {"NVDA": {"max_notional": 10}},
                },
            )
            write_json(
                root / "runtime" / "state" / "runs" / "2026-06-14" / "planner" / "dynamic_allowlist.json",
                {"date": "2026-06-14", "symbol_scores": {"NVDA": {"score": 88}}},
            )
            write_json(
                root / "runtime" / "state" / "runs" / "2026-06-14" / "planner" / "candidate_scores.json",
                {"date": "2026-06-14", "symbols": {"NVDA": {"total_score": 88, "components": {"technical": 80}}}},
            )
            write_json(
                root / "runtime" / "state" / "runs" / "2026-06-14" / "planner" / "risk_overlay.json",
                {"date": "2026-06-14", "market_regime": "aggressive_ok", "symbol_trade_rules": {"NVDA": {"allow_buy": True}}},
            )
            write_json(
                root / "runtime" / "state" / "runs" / "2026-06-14" / "planner" / "trader_watch_levels.json",
                {"symbols": {"NVDA": {"entry_low": 99.5, "entry_high": 100.5}}},
            )
            write_json(
                root / "runtime" / "state" / "runs" / "2026-06-14" / "planner" / "data_status_summary.json",
                {"date": "2026-06-14", "execution_blocking": False, "reason_codes": []},
            )
            write_json(
                root / "runtime" / "state" / "runs" / "2026-06-14" / "planner" / "capital_snapshot.json",
                {"date": "2026-06-14", "sizing_buying_power": 25.0},
            )
            write_json(
                root / "runtime" / "state" / "runs" / "2026-06-14" / "planner" / "catalyst_snapshot.json",
                {"date": "2026-06-14", "symbols": {"NVDA": {"score": 72}}},
            )
            write_json(
                root / "runtime" / "state" / "runs" / "2026-06-14" / "signals" / "technical_signals.json",
                {
                    "date": "2026-06-14",
                    "symbols": {
                        "NVDA": {
                            "long_setup": {
                                "status": "active",
                                "trigger_above": 100.5,
                                "entry_zone": {"low": 99.5, "high": 100.5},
                                "invalidation_below": 99.0,
                            },
                            "short_setup": {"status": "watch", "trigger_below": 98.5},
                            "no_trade_zone": {"low": 100.6, "high": 100.9, "reason": "range chop"},
                        }
                    },
                },
            )
            write_json(
                root / "runtime" / "state" / "runs" / "2026-06-14" / "planner" / "daily_usage.json",
                {"date": "2026-06-14", "used_notional": 5},
            )
            write_json(
                root / "runtime" / "state" / "runs" / "2026-06-14" / "research_reports" / "NVDA.json",
                {
                    "date": "2026-06-14",
                    "symbol": "NVDA",
                    "research_bias": "bullish",
                    "risk_flags": [],
                },
            )

            inputs = load_policy_inputs(root, run_date="2026-06-14", trading_mode="paper", risk_tier=0)

        self.assertEqual(inputs.universe, ["NVDA", "SMH"])
        self.assertEqual(inputs.today_allowlist, ["NVDA", "SMH"])
        self.assertEqual(inputs.risk_caps["max_single_order_notional"], 10)
        self.assertEqual(inputs.daily_plan["date"], "2026-06-14")
        self.assertEqual(inputs.dynamic_allowlist["symbol_scores"]["NVDA"]["score"], 88)
        self.assertEqual(inputs.candidate_scores["symbols"]["NVDA"]["total_score"], 88)
        self.assertEqual(inputs.risk_overlay["market_regime"], "aggressive_ok")
        self.assertEqual(inputs.trader_watch_levels["symbols"]["NVDA"]["entry_low"], 99.5)
        self.assertEqual(inputs.data_status_summary["execution_blocking"], False)
        self.assertEqual(inputs.capital_snapshot["sizing_buying_power"], 25.0)
        self.assertEqual(inputs.catalyst_snapshot["symbols"]["NVDA"]["score"], 72)
        self.assertEqual(inputs.policy_profile["name"], "aggressive_growth")
        self.assertEqual(inputs.technical_signals["symbols"]["NVDA"]["long_setup"]["status"], "active")
        self.assertEqual(inputs.daily_usage["used_notional"], 5)
        self.assertEqual(inputs.research_reports["NVDA"]["research_bias"], "bullish")

    def test_missing_required_state_is_represented_for_fail_closed_engine(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "src" / "config").mkdir(parents=True)
            (root / "runtime" / "state").mkdir(parents=True)
            (root / "src" / "config" / "universe.txt").write_text("NVDA\n", encoding="utf-8")
            write_json(
                root / "src" / "config" / "risk_tiers.json",
                {"0": {"max_single_order_notional": 10, "max_daily_notional": 25}},
            )

            inputs = load_policy_inputs(root, run_date="2026-06-14", trading_mode="paper", risk_tier=0)

        self.assertIsNone(inputs.daily_plan)
        self.assertEqual(inputs.today_allowlist, [])
        self.assertEqual(inputs.dynamic_allowlist, {})
        self.assertEqual(inputs.daily_usage, {})

    def test_load_policy_inputs_hydrates_robinhood_account_state(self) -> None:
        class FakeRobinhoodGateway:
            def get_account(self) -> dict[str, object]:
                return {"buying_power": "42.50", "account_type": "agentic"}

            def list_positions(self) -> list[dict[str, object]]:
                return [
                    {
                        "symbol": "nvda",
                        "quantity": "1.5",
                        "average_cost": "100.00",
                        "market_price": "104.00",
                    }
                ]

            def list_open_orders(self) -> list[dict[str, object]]:
                return [
                    {
                        "symbol": "SMH",
                        "side": "buy",
                        "quantity": "0.25",
                        "notional": "12.00",
                        "status": "queued",
                    }
                ]

            def get_quotes(self, symbols: list[str]) -> list[dict[str, object]]:
                self.requested_symbols = symbols
                return [
                    {
                        "symbol": "NVDA",
                        "price": "104.25",
                        "previous_close": "102.00",
                        "timestamp": "2026-06-14T09:45:00-07:00",
                        "is_fresh": True,
                    },
                    {"symbol": "SMH", "last_trade_price": "260.10", "previous_close": "259.00"},
                ]

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "src" / "config").mkdir(parents=True)
            (root / "runtime" / "state").mkdir(parents=True)
            (root / "src" / "config" / "universe.txt").write_text("NVDA\nSMH\n", encoding="utf-8")
            (root / "runtime" / "state" / "today_allowlist.txt").write_text("NVDA\nSMH\n", encoding="utf-8")
            write_json(
                root / "src" / "config" / "risk_tiers.json",
                {"0": {"max_single_order_notional": 10, "max_daily_notional": 25}},
            )
            write_json(
                root / "runtime" / "state" / "daily_plan.json",
                {"date": "2026-06-14", "today_watchlist": ["NVDA", "SMH"], "allowed_actions": []},
            )
            gateway = FakeRobinhoodGateway()

            inputs = load_policy_inputs(
                root,
                run_date="2026-06-14",
                trading_mode="paper",
                risk_tier=0,
                robinhood_gateway=gateway,
            )

        self.assertEqual(gateway.requested_symbols, ["NVDA", "SMH"])
        self.assertEqual(inputs.account["buying_power"], 42.5)
        self.assertEqual(inputs.positions["NVDA"].quantity, 1.5)
        self.assertEqual(inputs.positions["NVDA"].market_price, 104.0)
        self.assertEqual(inputs.open_orders[0].symbol, "SMH")
        self.assertEqual(inputs.open_orders[0].status, "queued")
        self.assertEqual(inputs.quotes["NVDA"].price, 104.25)
        self.assertEqual(inputs.quotes["SMH"].price, 260.10)

    def test_robinhood_gateway_failure_keeps_inputs_fail_closed(self) -> None:
        class FailingRobinhoodGateway:
            def get_account(self) -> dict[str, object]:
                raise RuntimeError("auth expired")

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "src" / "config").mkdir(parents=True)
            (root / "runtime" / "state").mkdir(parents=True)
            (root / "src" / "config" / "universe.txt").write_text("NVDA\n", encoding="utf-8")

            inputs = load_policy_inputs(
                root,
                run_date="2026-06-14",
                trading_mode="paper",
                risk_tier=0,
                robinhood_gateway=FailingRobinhoodGateway(),
            )

        self.assertEqual(inputs.account, {})
        self.assertEqual(inputs.quotes, {})
        self.assertEqual(inputs.positions, {})
        self.assertEqual(inputs.open_orders, [])

    def test_load_policy_inputs_reads_premarket_account_and_quote_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "src" / "config").mkdir(parents=True)
            (root / "runtime" / "state" / "runs" / "2026-06-14" / "planner").mkdir(parents=True)
            (root / "src" / "config" / "universe.txt").write_text("NVDA\nSMH\n", encoding="utf-8")
            (root / "runtime" / "state" / "runs" / "2026-06-14" / "planner" / "today_allowlist.txt").write_text("NVDA\nSMH\n", encoding="utf-8")
            write_json(root / "src" / "config" / "risk_tiers.json", {"0": {"max_single_order_notional": 10, "max_daily_notional": 25}})
            write_json(
                root / "runtime" / "state" / "runs" / "2026-06-14" / "planner" / "daily_plan.json",
                {
                    "date": "2026-06-14",
                    "market_regime": "normal",
                    "allowed_actions": ["small_limit_buy"],
                    "today_watchlist": ["NVDA", "SMH"],
                    "symbol_trade_rules": {"NVDA": {"max_notional": 10}},
                },
            )
            write_json(
                root / "runtime" / "state" / "runs" / "2026-06-14" / "planner" / "account_snapshot.json",
                {
                    "data_status": "ok",
                    "agentic_account_identified": True,
                    "buying_power": "31.25",
                    "current_positions": [{"symbol": "NVDA", "quantity": "1", "average_cost": "100", "market_price": "105"}],
                    "open_orders": [{"symbol": "SMH", "side": "buy", "quantity": "0.1", "notional": "26", "status": "queued"}],
                },
            )
            write_json(
                root / "runtime" / "state" / "runs" / "2026-06-14" / "planner" / "quote_snapshot_core.json",
                {"symbols": {"NVDA": {"last_price": "105.50", "previous_close": "103.00"}}},
            )
            write_json(
                root / "runtime" / "state" / "runs" / "2026-06-14" / "planner" / "quote_snapshot_candidates.json",
                {"symbols": {"SMH": {"last_price": "260.10", "previous_close": "259.00"}}},
            )

            inputs = load_policy_inputs(root, run_date="2026-06-14", trading_mode="paper", risk_tier=0)

        self.assertEqual(inputs.account["buying_power"], 31.25)
        self.assertEqual(inputs.positions["NVDA"].quantity, 1.0)
        self.assertEqual(inputs.open_orders[0].symbol, "SMH")
        self.assertEqual(inputs.quotes["NVDA"].price, 105.5)
        self.assertEqual(inputs.quotes["SMH"].price, 260.1)

    def test_load_policy_inputs_hydrates_pending_paper_orders_as_open_orders(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "src" / "config").mkdir(parents=True)
            planner_dir = root / "runtime" / "state" / "runs" / "2026-06-14" / "planner"
            paper_dir = root / "runtime" / "state" / "runs" / "2026-06-14" / "paper"
            planner_dir.mkdir(parents=True)
            paper_dir.mkdir(parents=True)
            (root / "src" / "config" / "universe.txt").write_text("NVDA\n", encoding="utf-8")
            (planner_dir / "today_allowlist.txt").write_text("NVDA\n", encoding="utf-8")
            write_json(root / "src" / "config" / "risk_tiers.json", {"0": {"max_single_order_notional": 10, "max_daily_notional": 25}})
            write_json(planner_dir / "daily_plan.json", {"date": "2026-06-14", "today_watchlist": ["NVDA"], "allowed_actions": ["small_limit_buy"]})
            write_json(paper_dir / "account.json", {"cash": 100.0})
            write_json(paper_dir / "positions.json", {})
            (paper_dir / "orders.jsonl").write_text(
                json.dumps(
                    {
                        "order_id": "paper-nvda-1",
                        "timestamp": "2026-06-14T09:45:00-07:00",
                        "symbol": "NVDA",
                        "side": "buy",
                        "quantity": 0.1,
                        "notional": 10.0,
                        "status": "pending",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            inputs = load_policy_inputs(root, run_date="2026-06-14", trading_mode="paper", risk_tier=0)

        self.assertEqual(len(inputs.open_orders), 1)
        self.assertEqual(inputs.open_orders[0].symbol, "NVDA")
        self.assertEqual(inputs.open_orders[0].status, "pending")

    def test_paper_mode_overrides_account_and_positions_from_paper_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "src" / "config").mkdir(parents=True)
            (root / "runtime" / "state" / "runs" / "2026-06-14" / "planner").mkdir(parents=True)
            (root / "src" / "config" / "universe.txt").write_text("NVDA\n", encoding="utf-8")
            (root / "runtime" / "state" / "runs" / "2026-06-14" / "planner" / "today_allowlist.txt").write_text("NVDA\n", encoding="utf-8")
            write_json(root / "src" / "config" / "risk_tiers.json", {"0": {"max_single_order_notional": 10, "max_daily_notional": 25}})
            write_json(
                root / "runtime" / "state" / "runs" / "2026-06-14" / "planner" / "daily_plan.json",
                {"date": "2026-06-14", "today_watchlist": ["NVDA"], "allowed_actions": ["small_limit_buy"]},
            )
            write_json(
                root / "runtime" / "state" / "runs" / "2026-06-14" / "planner" / "account_snapshot.json",
                {
                    "agentic_account_identified": True,
                    "buying_power": "100.00",
                    "current_positions": [{"symbol": "NVDA", "quantity": "5", "average_cost": "90", "market_price": "100"}],
                },
            )
            write_json(root / "runtime" / "state" / "runs" / "2026-06-14" / "planner" / "quote_snapshot_core.json", {"symbols": {"NVDA": {"last_price": "101.00"}}})
            write_json(root / "runtime" / "state" / "runs" / "2026-06-14" / "paper" / "account.json", {"cash": 14.25})
            write_json(
                root / "runtime" / "state" / "runs" / "2026-06-14" / "paper" / "positions.json",
                {"NVDA": {"symbol": "NVDA", "quantity": 0.1, "average_cost": 100.0, "market_price": 101.0}},
            )

            inputs = load_policy_inputs(root, run_date="2026-06-14", trading_mode="paper", risk_tier=0)

        self.assertEqual(inputs.account["buying_power"], 14.25)
        self.assertEqual(inputs.positions["NVDA"].quantity, 0.1)
        self.assertEqual(inputs.quotes["NVDA"].price, 101.0)


if __name__ == "__main__":
    unittest.main()
