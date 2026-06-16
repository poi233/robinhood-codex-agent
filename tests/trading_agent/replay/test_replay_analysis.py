from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from trading_agent.replay.analysis import (
    blocked_reason_summary,
    build_replay_report,
    collect_decisions,
    collect_paper_orders,
    discover_run_dates,
    fill_rate_summary,
    format_replay_report,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def _make_run(root: Path, run_date: str, *, orders: list[dict] | None = None, decisions: list[dict] | None = None) -> None:
    state_dir = root / "runtime" / "state" / "runs" / run_date / "paper"
    logs_dir = root / "runtime" / "logs" / "runs" / run_date / "audit"
    state_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    if orders is not None:
        _write_jsonl(state_dir / "orders.jsonl", orders)
    if decisions is not None:
        _write_jsonl(logs_dir / "decisions.jsonl", decisions)


class DiscoverRunDatesTests(unittest.TestCase):
    def test_finds_date_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _make_run(root, "2026-06-14")
            _make_run(root, "2026-06-15")
            dates = discover_run_dates(root)
            self.assertEqual(dates, ["2026-06-14", "2026-06-15"])

    def test_since_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _make_run(root, "2026-06-13")
            _make_run(root, "2026-06-14")
            _make_run(root, "2026-06-15")
            dates = discover_run_dates(root, since_date="2026-06-14")
            self.assertEqual(dates, ["2026-06-14", "2026-06-15"])

    def test_until_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _make_run(root, "2026-06-13")
            _make_run(root, "2026-06-14")
            _make_run(root, "2026-06-15")
            dates = discover_run_dates(root, until_date="2026-06-14")
            self.assertEqual(dates, ["2026-06-13", "2026-06-14"])

    def test_missing_dir_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertEqual(discover_run_dates(Path(tmpdir)), [])


class FillRateSummaryTests(unittest.TestCase):
    def test_empty_orders(self) -> None:
        result = fill_rate_summary([])
        self.assertEqual(result["total_orders"], 0)
        self.assertEqual(result["fill_rate_pct"], 0.0)

    def test_all_filled(self) -> None:
        orders = [
            {"symbol": "NVDA", "status": "filled", "quantity": 0.1, "limit_price": 100.0, "fill_price": 99.9, "notional": 10.0},
            {"symbol": "AMD", "status": "filled", "quantity": 0.2, "limit_price": 50.0, "fill_price": 49.95, "notional": 10.0},
        ]
        result = fill_rate_summary(orders)
        self.assertEqual(result["total_orders"], 2)
        self.assertEqual(result["filled"], 2)
        self.assertEqual(result["fill_rate_pct"], 100.0)
        self.assertEqual(result["canceled"], 0)

    def test_mixed_statuses(self) -> None:
        orders = [
            {"symbol": "NVDA", "status": "filled", "quantity": 0.1, "fill_price": 100.0, "notional": 10.0},
            {"symbol": "NVDA", "status": "pending_canceled", "quantity": 0.1, "limit_price": 100.0, "notional": 10.0},
            {"symbol": "AMD", "status": "pending", "quantity": 0.1, "limit_price": 50.0, "notional": 5.0},
        ]
        result = fill_rate_summary(orders)
        self.assertEqual(result["total_orders"], 3)
        self.assertEqual(result["filled"], 1)
        self.assertEqual(result["canceled"], 1)
        self.assertEqual(result["pending"], 1)
        self.assertAlmostEqual(result["fill_rate_pct"], 33.3, places=0)

    def test_by_symbol_sorted_by_fill_count(self) -> None:
        orders = [
            {"symbol": "AMD", "status": "filled", "quantity": 0.1, "fill_price": 50.0, "notional": 5.0},
            {"symbol": "NVDA", "status": "filled", "quantity": 0.1, "fill_price": 100.0, "notional": 10.0},
            {"symbol": "NVDA", "status": "filled", "quantity": 0.1, "fill_price": 100.0, "notional": 10.0},
        ]
        result = fill_rate_summary(orders)
        symbols = list(result["by_symbol"].keys())
        self.assertEqual(symbols[0], "NVDA")  # 2 fills, sorted first

    def test_resolve_final_orders_pending_then_filled(self) -> None:
        # An order goes: pending → pending_filled
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            rows = [
                {"order_id": "p-nvda-1", "symbol": "NVDA", "side": "buy", "quantity": 0.1,
                 "limit_price": 100.0, "notional": 10.0, "status": "pending"},
                {"order_id": "p-nvda-1", "event": "pending_filled", "status": "filled",
                 "fill_price": 99.9, "timestamp": "2026-06-15T10:30:00-07:00"},
            ]
            _make_run(root, "2026-06-15", orders=rows)
            orders = collect_paper_orders(root, run_dates=["2026-06-15"])
            self.assertEqual(len(orders), 1)
            self.assertEqual(orders[0]["status"], "filled")
            self.assertEqual(orders[0]["fill_price"], 99.9)

    def test_resolve_final_orders_pending_then_canceled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            rows = [
                {"order_id": "p-nvda-2", "symbol": "NVDA", "side": "buy", "quantity": 0.1,
                 "limit_price": 100.0, "notional": 10.0, "status": "pending"},
                {"order_id": "p-nvda-2", "event": "day_end_cancel", "status": "pending_canceled",
                 "timestamp": "2026-06-15T16:00:00-07:00"},
            ]
            _make_run(root, "2026-06-15", orders=rows)
            orders = collect_paper_orders(root, run_dates=["2026-06-15"])
            self.assertEqual(len(orders), 1)
            self.assertEqual(orders[0]["status"], "pending_canceled")


class BlockedReasonSummaryTests(unittest.TestCase):
    def test_empty_decisions(self) -> None:
        result = blocked_reason_summary([])
        self.assertEqual(result["total_evaluations"], 0)
        self.assertEqual(result["reason_counts"], {})

    def test_counts_reasons(self) -> None:
        decisions = [
            {"decision": "no_trade", "blocked_reasons": ["outside_entry_zone", "reward_risk_too_low"]},
            {"decision": "no_trade", "blocked_reasons": ["outside_entry_zone"]},
            {"decision": "would_trade", "blocked_reasons": []},
        ]
        result = blocked_reason_summary(decisions)
        self.assertEqual(result["total_evaluations"], 3)
        self.assertEqual(result["would_trade"], 1)
        self.assertEqual(result["no_trade"], 2)
        self.assertEqual(result["reason_counts"]["outside_entry_zone"], 2)
        self.assertEqual(result["reason_counts"]["reward_risk_too_low"], 1)

    def test_reason_counts_sorted_by_frequency(self) -> None:
        decisions = [
            {"decision": "no_trade", "blocked_reasons": ["outside_entry_zone"]},
            {"decision": "no_trade", "blocked_reasons": ["outside_entry_zone"]},
            {"decision": "no_trade", "blocked_reasons": ["reward_risk_too_low"]},
        ]
        result = blocked_reason_summary(decisions)
        keys = list(result["reason_counts"].keys())
        self.assertEqual(keys[0], "outside_entry_zone")


class BuildReplayReportTests(unittest.TestCase):
    def test_no_run_dates_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report = build_replay_report(Path(tmpdir))
            self.assertEqual(report["error"], "no_run_dates_found")
            self.assertEqual(report["run_date_count"], 0)

    def test_full_report_with_fixture_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            orders = [
                {"order_id": "p-nvda-1", "symbol": "NVDA", "side": "buy", "quantity": 0.1,
                 "limit_price": 100.0, "notional": 10.0, "status": "filled", "fill_price": 99.9},
                {"order_id": "p-amd-1", "symbol": "AMD", "side": "buy", "quantity": 0.2,
                 "limit_price": 50.0, "notional": 10.0, "status": "pending_canceled"},
            ]
            decisions = [
                {"decision": "would_trade", "blocked_reasons": []},
                {"decision": "no_trade", "blocked_reasons": ["outside_entry_zone"]},
                {"decision": "no_trade", "blocked_reasons": ["reward_risk_too_low"]},
            ]
            _make_run(root, "2026-06-15", orders=orders, decisions=decisions)
            report = build_replay_report(root)
            self.assertEqual(report["run_date_count"], 1)
            self.assertEqual(report["fill_rate"]["total_orders"], 2)
            self.assertEqual(report["fill_rate"]["filled"], 1)
            self.assertAlmostEqual(report["fill_rate"]["fill_rate_pct"], 50.0)
            self.assertEqual(report["blocked_reasons"]["total_evaluations"], 3)
            self.assertEqual(report["blocked_reasons"]["would_trade"], 1)

    def test_format_report_is_non_empty_string(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _make_run(root, "2026-06-15", orders=[], decisions=[])
            report = build_replay_report(root)
            text = format_replay_report(report)
            self.assertIn("Replay Report", text)
            self.assertIn("Fill Rate", text)
            self.assertIn("Blocked Reason", text)

    def test_since_filter_applied(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _make_run(root, "2026-06-13", orders=[
                {"order_id": "p-1", "symbol": "SPY", "status": "filled", "quantity": 0.1,
                 "fill_price": 500.0, "notional": 50.0},
            ])
            _make_run(root, "2026-06-15", orders=[])
            report = build_replay_report(root, since_date="2026-06-15")
            self.assertEqual(report["run_dates"], ["2026-06-15"])
            self.assertEqual(report["fill_rate"]["total_orders"], 0)


if __name__ == "__main__":
    unittest.main()
