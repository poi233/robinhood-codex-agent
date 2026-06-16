import json
import os
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from trading_agent.paper.broker import apply_paper_intent, pending_paper_orders, reconcile_pending_paper_orders, record_paper_day_end, record_paper_day_start
from trading_agent.paper.broker import _compute_fill_price, _partial_fill_ratio, _resolve_fill_quantity
from trading_agent.policy.models import OrderIntent, PolicyDecision, Quote


class PaperBrokerTests(unittest.TestCase):
    def test_apply_buy_intent_initializes_account_and_updates_position(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            decision = PolicyDecision(
                trading_mode="paper",
                checked_symbols=["NVDA"],
                decision="would_trade",
                intent=OrderIntent(
                    symbol="NVDA",
                    side="buy",
                    order_type="limit",
                    limit_price=100.0,
                    reference_price=100.0,
                    estimated_notional=10.0,
                    quantity=0.1,
                    reason_codes=["score_pass"],
                    confidence=0.85,
                ),
            )

            with unittest.mock.patch.dict(os.environ, {"PAPER_FILL_MODEL": "conservative"}, clear=False):
                result = apply_paper_intent(root, run_date="2026-06-14", decision=decision, starting_cash=25.0)

            account = json.loads((root / "runtime" / "state" / "runs" / "2026-06-14" / "paper" / "account.json").read_text(encoding="utf-8"))
            positions = json.loads((root / "runtime" / "state" / "runs" / "2026-06-14" / "paper" / "positions.json").read_text(encoding="utf-8"))
            order_line = (root / "runtime" / "state" / "runs" / "2026-06-14" / "paper" / "orders.jsonl").read_text(encoding="utf-8").splitlines()[0]
            order = json.loads(order_line)
            usage = json.loads((root / "runtime" / "state" / "runs" / "2026-06-14" / "planner" / "daily_usage.json").read_text(encoding="utf-8"))
            day_start = json.loads((root / "runtime" / "state" / "runs" / "2026-06-14" / "paper" / "day_start.json").read_text(encoding="utf-8"))
            curve = [
                json.loads(line)
                for line in (root / "runtime" / "state" / "runs" / "2026-06-14" / "paper" / "equity_curve.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]

        self.assertTrue(result.applied)
        self.assertEqual(account["cash"], 15.0)
        self.assertEqual(positions["NVDA"]["quantity"], 0.1)
        self.assertEqual(positions["NVDA"]["average_cost"], 100.0)
        self.assertEqual(order["symbol"], "NVDA")
        self.assertEqual(order["side"], "buy")
        self.assertEqual(order["status"], "filled")
        self.assertEqual(order["current_price_at_submit"], 100.0)
        self.assertEqual(usage["date"], "2026-06-14")
        self.assertEqual(usage["used_notional"], 10.0)
        self.assertEqual(usage["paper_filled_notional"], 10.0)
        self.assertEqual(usage["paper_order_count"], 1)
        self.assertEqual(usage["new_positions_today"], 1)
        self.assertEqual(usage["last_buy_date_by_symbol"]["NVDA"], "2026-06-14")
        self.assertEqual(day_start["cash"], 25.0)
        self.assertEqual(day_start["total_equity"], 25.0)
        self.assertEqual(curve[0]["event"], "day_start")
        self.assertEqual(curve[-1]["event"], "fill")
        self.assertEqual(curve[-1]["cash"], 15.0)
        self.assertEqual(curve[-1]["positions_market_value"], 10.0)
        self.assertEqual(curve[-1]["total_equity"], 25.0)

    def test_apply_buy_intent_accumulates_existing_daily_usage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            usage_path = root / "runtime" / "state" / "runs" / "2026-06-14" / "planner" / "daily_usage.json"
            usage_path.parent.mkdir(parents=True)
            usage_path.write_text(json.dumps({"date": "2026-06-14", "used_notional": 5.5}), encoding="utf-8")
            decision = PolicyDecision(
                trading_mode="paper",
                checked_symbols=["NVDA"],
                decision="would_trade",
                intent=OrderIntent(
                    symbol="NVDA",
                    side="buy",
                    order_type="limit",
                    limit_price=100.0,
                    reference_price=100.0,
                    estimated_notional=10.0,
                    quantity=0.1,
                ),
            )

            with unittest.mock.patch.dict(os.environ, {"PAPER_FILL_MODEL": "conservative"}, clear=False):
                result = apply_paper_intent(root, run_date="2026-06-14", decision=decision, starting_cash=25.0)
            usage = json.loads(usage_path.read_text(encoding="utf-8"))

        self.assertTrue(result.applied)
        self.assertEqual(usage["used_notional"], 15.5)
        self.assertEqual(usage["paper_filled_notional"], 10.0)
        self.assertEqual(usage["paper_order_count"], 1)

    def test_conservative_buy_limit_can_remain_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            decision = PolicyDecision(
                trading_mode="paper",
                checked_symbols=["NVDA"],
                decision="would_trade",
                intent=OrderIntent(
                    symbol="NVDA",
                    side="buy",
                    order_type="limit",
                    limit_price=100.0,
                    reference_price=101.0,
                    estimated_notional=10.0,
                    quantity=0.1,
                ),
            )

            with unittest.mock.patch.dict(os.environ, {"PAPER_FILL_MODEL": "conservative"}, clear=False):
                result = apply_paper_intent(root, run_date="2026-06-14", decision=decision, starting_cash=25.0)

            order_line = (root / "runtime" / "state" / "runs" / "2026-06-14" / "paper" / "orders.jsonl").read_text(encoding="utf-8").splitlines()[0]
            order = json.loads(order_line)
            usage_path = root / "runtime" / "state" / "runs" / "2026-06-14" / "planner" / "daily_usage.json"

        self.assertFalse(result.applied)
        self.assertEqual(result.status, "pending")
        self.assertEqual(order["status"], "pending")
        self.assertEqual(order["unfilled_reason"], "buy_limit_not_reached")
        self.assertFalse(usage_path.exists())

    def test_daily_usage_resets_new_day_and_new_week_counters(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            usage_path = root / "runtime" / "state" / "runs" / "2026-06-16" / "planner" / "daily_usage.json"
            usage_path.parent.mkdir(parents=True)
            usage_path.write_text(
                json.dumps(
                    {
                        "date": "2026-06-13",
                        "used_notional": 40.0,
                        "paper_filled_notional": 20.0,
                        "paper_order_count": 2,
                        "new_positions_today": 2,
                        "new_positions_this_week": 4,
                        "new_position_symbols_today": ["NVDA", "SMH"],
                    }
                ),
                encoding="utf-8",
            )
            decision = PolicyDecision(
                trading_mode="paper",
                checked_symbols=["NVDA"],
                decision="would_trade",
                intent=OrderIntent(
                    symbol="NVDA",
                    side="buy",
                    order_type="limit",
                    limit_price=100.0,
                    reference_price=100.0,
                    estimated_notional=10.0,
                    quantity=0.1,
                ),
            )

            with unittest.mock.patch.dict(os.environ, {"PAPER_FILL_MODEL": "conservative"}, clear=False):
                result = apply_paper_intent(root, run_date="2026-06-16", decision=decision, starting_cash=50.0)
            usage = json.loads(usage_path.read_text(encoding="utf-8"))

        self.assertTrue(result.applied)
        self.assertEqual(usage["date"], "2026-06-16")
        self.assertEqual(usage["used_notional"], 10.0)
        self.assertEqual(usage["paper_order_count"], 1)
        self.assertEqual(usage["new_positions_today"], 1)
        self.assertEqual(usage["new_positions_this_week"], 1)

    def test_pending_order_reconciles_to_fill_on_later_intraday_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            decision = PolicyDecision(
                trading_mode="paper",
                checked_symbols=["NVDA"],
                decision="would_trade",
                intent=OrderIntent(
                    symbol="NVDA",
                    side="buy",
                    order_type="limit",
                    limit_price=100.0,
                    reference_price=101.0,
                    estimated_notional=10.0,
                    quantity=0.1,
                ),
            )
            with unittest.mock.patch.dict(os.environ, {"PAPER_FILL_MODEL": "conservative"}, clear=False):
                pending = apply_paper_intent(root, run_date="2026-06-14", decision=decision, starting_cash=25.0)
                events = reconcile_pending_paper_orders(
                    root,
                    run_date="2026-06-14",
                    quotes={"NVDA": Quote(symbol="NVDA", price=99.5, timestamp="2026-06-14T10:15:00-07:00", is_fresh=True)},
                    starting_cash=25.0,
                )
            account = json.loads((root / "runtime" / "state" / "runs" / "2026-06-14" / "paper" / "account.json").read_text(encoding="utf-8"))
            positions = json.loads((root / "runtime" / "state" / "runs" / "2026-06-14" / "paper" / "positions.json").read_text(encoding="utf-8"))
            usage = json.loads((root / "runtime" / "state" / "runs" / "2026-06-14" / "planner" / "daily_usage.json").read_text(encoding="utf-8"))
            active_pending = pending_paper_orders(root, run_date="2026-06-14")

        # With PAPER_SLIPPAGE_BPS=10 (default): fill_price = min(100, 99.5*1.001) = 99.5995
        # notional = 0.1 * 99.5995 = 9.9600 (rounded to 2dp)
        # cash remaining = 25.0 - 9.96 = 15.04
        expected_fill_price = round(min(100.0, 99.5 * 1.001), 4)
        expected_notional = round(0.1 * expected_fill_price, 2)
        self.assertFalse(pending.applied)
        self.assertEqual(pending.status, "pending")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["status"], "filled")
        self.assertAlmostEqual(account["cash"], round(25.0 - expected_notional, 2), places=2)
        self.assertEqual(positions["NVDA"]["quantity"], 0.1)
        self.assertAlmostEqual(usage["paper_filled_notional"], expected_notional, places=2)
        self.assertEqual(active_pending, [])

    def test_slippage_reduces_buy_fill_below_limit_when_reference_below_limit(self) -> None:
        self.assertAlmostEqual(_compute_fill_price("buy", 100.0, 98.0, 0.001), 98.098, places=3)
        self.assertEqual(_compute_fill_price("buy", 100.0, 100.0, 0.001), 100.0)
        self.assertAlmostEqual(_compute_fill_price("sell", 99.0, 101.0, 0.001), 100.899, places=3)

    def test_buy_fill_accounting_uses_slippage_price(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            decision = PolicyDecision(
                trading_mode="paper",
                checked_symbols=["NVDA"],
                decision="would_trade",
                intent=OrderIntent(
                    symbol="NVDA",
                    side="buy",
                    order_type="limit",
                    limit_price=100.0,
                    reference_price=98.0,
                    estimated_notional=9.8,
                    quantity=0.1,
                ),
            )
            # fill_price = min(100.0, 98.0 * 1.001) = 98.098
            with unittest.mock.patch.dict(os.environ, {"PAPER_FILL_MODEL": "conservative", "PAPER_SLIPPAGE_BPS": "10"}, clear=False):
                result = apply_paper_intent(root, run_date="2026-06-14", decision=decision, starting_cash=200.0)

            account = json.loads((root / "runtime" / "state" / "runs" / "2026-06-14" / "paper" / "account.json").read_text(encoding="utf-8"))
            positions = json.loads((root / "runtime" / "state" / "runs" / "2026-06-14" / "paper" / "positions.json").read_text(encoding="utf-8"))
            order_line = (root / "runtime" / "state" / "runs" / "2026-06-14" / "paper" / "orders.jsonl").read_text(encoding="utf-8").splitlines()[0]
            order = json.loads(order_line)

        self.assertTrue(result.applied)
        expected_fill = round(min(100.0, 98.0 * 1.001), 4)  # 98.098
        expected_notional = round(0.1 * expected_fill, 2)    # 9.81 (rounded 2dp)
        expected_avg_cost = round(expected_notional / 0.1, 4)  # derived from rounded notional
        self.assertAlmostEqual(order["fill_price"], expected_fill, places=3)
        self.assertEqual(order["limit_price"], 100.0)
        self.assertAlmostEqual(account["cash"], round(200.0 - expected_notional, 2), places=2)
        self.assertAlmostEqual(positions["NVDA"]["average_cost"], expected_avg_cost, places=3)

    def test_day_end_cancels_pending_orders_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            decision = PolicyDecision(
                trading_mode="paper",
                checked_symbols=["NVDA"],
                decision="would_trade",
                intent=OrderIntent(
                    symbol="NVDA",
                    side="buy",
                    order_type="limit",
                    limit_price=100.0,
                    reference_price=101.0,
                    estimated_notional=10.0,
                    quantity=0.1,
                ),
            )
            with unittest.mock.patch.dict(os.environ, {"PAPER_FILL_MODEL": "conservative"}, clear=False):
                apply_paper_intent(root, run_date="2026-06-14", decision=decision, starting_cash=200.0)
                remaining_before = pending_paper_orders(root, run_date="2026-06-14")
                record_paper_day_end(root, run_date="2026-06-14")
                remaining_after = pending_paper_orders(root, run_date="2026-06-14")
            orders_log = (root / "runtime" / "state" / "runs" / "2026-06-14" / "paper" / "orders.jsonl").read_text(encoding="utf-8").splitlines()
            cancel_events = [json.loads(line) for line in orders_log if json.loads(line).get("event") == "day_end_cancel"]

        self.assertEqual(len(remaining_before), 1)
        self.assertEqual(len(remaining_after), 0)
        self.assertEqual(len(cancel_events), 1)
        self.assertEqual(cancel_events[0]["status"], "pending_canceled")
        self.assertEqual(cancel_events[0]["reason"], "day_end_expired")

    def test_day_start_is_not_overwritten_and_day_end_records_current_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            first = record_paper_day_start(root, run_date="2026-06-14", starting_cash=25.0)
            second = record_paper_day_start(root, run_date="2026-06-14", starting_cash=99.0)
            result = record_paper_day_end(root, run_date="2026-06-14")

            paper_dir = root / "runtime" / "state" / "runs" / "2026-06-14" / "paper"
            day_start = json.loads((paper_dir / "day_start.json").read_text(encoding="utf-8"))
            day_end = json.loads((paper_dir / "day_end.json").read_text(encoding="utf-8"))
            curve = [json.loads(line) for line in (paper_dir / "equity_curve.jsonl").read_text(encoding="utf-8").splitlines()]

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertTrue(result)
        self.assertEqual(day_start["cash"], 25.0)
        self.assertEqual(day_end["cash"], 25.0)
        self.assertEqual(day_end["total_equity"], 25.0)
        self.assertEqual([point["event"] for point in curve], ["day_start", "day_end"])


    def test_partial_fill_ratio_at_limit_is_min_ratio(self) -> None:
        with unittest.mock.patch.dict(os.environ, {"PAPER_PARTIAL_FILL_MIN_RATIO": "0.3", "PAPER_PARTIAL_FILL_THRESHOLD_BPS": "20"}, clear=False):
            self.assertAlmostEqual(_partial_fill_ratio("buy", 100.0, 100.0), 0.3, places=3)

    def test_partial_fill_ratio_solidly_through_limit_is_full(self) -> None:
        with unittest.mock.patch.dict(os.environ, {"PAPER_PARTIAL_FILL_MIN_RATIO": "0.3", "PAPER_PARTIAL_FILL_THRESHOLD_BPS": "20"}, clear=False):
            # 20bps through a $100 limit = $99.80 or lower for a buy.
            self.assertEqual(_partial_fill_ratio("buy", 100.0, 99.5), 1.0)

    def test_partial_fill_ratio_interpolates_between_min_and_full(self) -> None:
        with unittest.mock.patch.dict(os.environ, {"PAPER_PARTIAL_FILL_MIN_RATIO": "0.3", "PAPER_PARTIAL_FILL_THRESHOLD_BPS": "20"}, clear=False):
            # 10bps through (halfway to the 20bps threshold) => halfway between 0.3 and 1.0.
            ratio = _partial_fill_ratio("buy", 100.0, 99.9)
            self.assertAlmostEqual(ratio, 0.65, places=2)

    def test_resolve_fill_quantity_returns_full_quantity_when_disabled(self) -> None:
        intent = OrderIntent(
            symbol="NVDA", side="buy", order_type="limit", limit_price=100.0,
            reference_price=100.0, estimated_notional=10.0, quantity=0.1,
        )
        with unittest.mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PAPER_PARTIAL_FILL", None)
            filled_qty, remaining_qty = _resolve_fill_quantity(intent)
        self.assertEqual(filled_qty, 0.1)
        self.assertEqual(remaining_qty, 0.0)

    def test_apply_buy_intent_partial_fills_when_quote_just_clears_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            decision = PolicyDecision(
                trading_mode="paper",
                checked_symbols=["NVDA"],
                decision="would_trade",
                intent=OrderIntent(
                    symbol="NVDA",
                    side="buy",
                    order_type="limit",
                    limit_price=100.0,
                    reference_price=100.0,
                    estimated_notional=10.0,
                    quantity=0.1,
                ),
            )

            with unittest.mock.patch.dict(
                os.environ,
                {
                    "PAPER_FILL_MODEL": "conservative",
                    "PAPER_PARTIAL_FILL": "1",
                    "PAPER_PARTIAL_FILL_MIN_RATIO": "0.3",
                    "PAPER_PARTIAL_FILL_THRESHOLD_BPS": "20",
                    "PAPER_SLIPPAGE_BPS": "0",
                },
                clear=False,
            ):
                result = apply_paper_intent(root, run_date="2026-06-14", decision=decision, starting_cash=25.0)
                active_pending = pending_paper_orders(root, run_date="2026-06-14")

            positions = json.loads((root / "runtime" / "state" / "runs" / "2026-06-14" / "paper" / "positions.json").read_text(encoding="utf-8"))
            usage = json.loads((root / "runtime" / "state" / "runs" / "2026-06-14" / "planner" / "daily_usage.json").read_text(encoding="utf-8"))
            orders_log = [
                json.loads(line)
                for line in (root / "runtime" / "state" / "runs" / "2026-06-14" / "paper" / "orders.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]

        self.assertTrue(result.applied)
        self.assertEqual(result.status, "filled")
        initial_order = orders_log[0]
        self.assertEqual(initial_order["status"], "partial_filled")
        self.assertAlmostEqual(initial_order["filled_qty"], 0.03, places=6)
        self.assertAlmostEqual(initial_order["remaining_qty"], 0.07, places=6)
        self.assertEqual(initial_order["original_quantity"], 0.1)
        self.assertAlmostEqual(positions["NVDA"]["quantity"], 0.03, places=6)
        self.assertAlmostEqual(usage["paper_filled_notional"], 3.0, places=2)
        # The remainder re-queues as a smaller pending order under the same order_id.
        self.assertEqual(len(active_pending), 1)
        self.assertEqual(active_pending[0]["order_id"], initial_order["order_id"])
        self.assertAlmostEqual(active_pending[0]["quantity"], 0.07, places=6)

    def test_reconcile_fills_remaining_quantity_once_quote_clears_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            decision = PolicyDecision(
                trading_mode="paper",
                checked_symbols=["NVDA"],
                decision="would_trade",
                intent=OrderIntent(
                    symbol="NVDA",
                    side="buy",
                    order_type="limit",
                    limit_price=100.0,
                    reference_price=100.0,
                    estimated_notional=10.0,
                    quantity=0.1,
                ),
            )
            env = {
                "PAPER_FILL_MODEL": "conservative",
                "PAPER_PARTIAL_FILL": "1",
                "PAPER_PARTIAL_FILL_MIN_RATIO": "0.3",
                "PAPER_PARTIAL_FILL_THRESHOLD_BPS": "20",
                "PAPER_SLIPPAGE_BPS": "0",
            }
            with unittest.mock.patch.dict(os.environ, env, clear=False):
                apply_paper_intent(root, run_date="2026-06-14", decision=decision, starting_cash=25.0)
                # Quote now sits comfortably through the limit -> remainder fills in full.
                events = reconcile_pending_paper_orders(
                    root,
                    run_date="2026-06-14",
                    quotes={"NVDA": Quote(symbol="NVDA", price=99.0, timestamp="2026-06-14T10:15:00-07:00", is_fresh=True)},
                    starting_cash=25.0,
                )
                active_pending = pending_paper_orders(root, run_date="2026-06-14")

            positions = json.loads((root / "runtime" / "state" / "runs" / "2026-06-14" / "paper" / "positions.json").read_text(encoding="utf-8"))

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["status"], "filled")
        self.assertAlmostEqual(positions["NVDA"]["quantity"], 0.1, places=6)
        self.assertEqual(active_pending, [])


if __name__ == "__main__":
    unittest.main()
