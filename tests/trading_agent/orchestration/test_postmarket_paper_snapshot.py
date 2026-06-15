import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from trading_agent.orchestration import postmarket as postmarket_module


class PostmarketPaperSnapshotTests(unittest.TestCase):
    def test_postmarket_records_paper_day_end_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            paper_dir = root / "runtime" / "state" / "runs" / "2026-06-14" / "paper"
            paper_dir.mkdir(parents=True)
            (root / "src" / "config").mkdir(parents=True)
            (root / "src" / "config" / "runtime.env").write_text("TRADING_MODE=paper\n", encoding="utf-8")
            (paper_dir / "account.json").write_text(
                json.dumps({"cash": 15.0, "starting_cash": 25.0, "realized_pnl": 0.0}),
                encoding="utf-8",
            )
            (paper_dir / "positions.json").write_text(
                json.dumps({"NVDA": {"symbol": "NVDA", "quantity": 0.1, "average_cost": 100.0, "market_price": 100.0}}),
                encoding="utf-8",
            )

            original_cwd = os.getcwd()
            os.chdir(root)
            try:
                with mock.patch.object(postmarket_module, "_is_weekday_pt", return_value=True), \
                    mock.patch.dict(os.environ, {"RUN_DATE_PT": "2026-06-14"}, clear=False), \
                    mock.patch.object(postmarket_module, "run_codex_prompt", return_value=0):
                    status = postmarket_module.run_postmarket_pipeline(dry_run=False)

                day_end = json.loads((paper_dir / "day_end.json").read_text(encoding="utf-8"))
                curve = [json.loads(line) for line in (paper_dir / "equity_curve.jsonl").read_text(encoding="utf-8").splitlines()]
            finally:
                os.chdir(original_cwd)

        self.assertEqual(status, 0)
        self.assertEqual(day_end["cash"], 15.0)
        self.assertEqual(day_end["positions_market_value"], 10.0)
        self.assertEqual(day_end["total_equity"], 25.0)
        self.assertEqual(curve[-1]["event"], "day_end")

    def test_postmarket_writes_paper_summary_before_codex_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            paper_dir = root / "runtime" / "state" / "runs" / "2026-06-14" / "paper"
            planner_dir = root / "runtime" / "state" / "runs" / "2026-06-14" / "planner"
            paper_dir.mkdir(parents=True)
            planner_dir.mkdir(parents=True)
            (root / "src" / "config").mkdir(parents=True)
            (root / "src" / "config" / "runtime.env").write_text("TRADING_MODE=paper\n", encoding="utf-8")
            (paper_dir / "day_start.json").write_text(
                json.dumps(
                    {
                        "cash": 1000.0,
                        "positions_market_value": 100.0,
                        "total_equity": 1100.0,
                        "positions": {"NVDA": {"symbol": "NVDA", "quantity": 1, "market_price": 100.0}},
                    }
                ),
                encoding="utf-8",
            )
            (paper_dir / "account.json").write_text(
                json.dumps({"cash": 890.0, "starting_cash": 1000.0, "realized_pnl": 5.0}),
                encoding="utf-8",
            )
            (paper_dir / "positions.json").write_text(
                json.dumps(
                    {
                        "NVDA": {"symbol": "NVDA", "quantity": 1, "average_cost": 100.0, "market_price": 110.0},
                        "PLTR": {"symbol": "PLTR", "quantity": 2, "average_cost": 50.0, "market_price": 55.0},
                    }
                ),
                encoding="utf-8",
            )
            (paper_dir / "orders.jsonl").write_text(
                json.dumps({"symbol": "PLTR", "side": "buy", "status": "filled", "notional": 110.0}) + "\n",
                encoding="utf-8",
            )
            (planner_dir / "daily_usage.json").write_text(
                json.dumps({"used_notional": 110.0, "paper_filled_notional": 110.0, "paper_order_count": 1}),
                encoding="utf-8",
            )

            observed_summary_exists_at_prompt = False

            def fake_run_codex_prompt(*_args: object) -> int:
                nonlocal observed_summary_exists_at_prompt
                observed_summary_exists_at_prompt = (paper_dir / "postmarket_summary.json").exists()
                return 0

            original_cwd = os.getcwd()
            os.chdir(root)
            try:
                with mock.patch.object(postmarket_module, "_is_weekday_pt", return_value=True), \
                    mock.patch.dict(os.environ, {"RUN_DATE_PT": "2026-06-14"}, clear=False), \
                    mock.patch.object(postmarket_module, "run_codex_prompt", side_effect=fake_run_codex_prompt):
                    status = postmarket_module.run_postmarket_pipeline(dry_run=False)

                summary = json.loads((paper_dir / "postmarket_summary.json").read_text(encoding="utf-8"))
            finally:
                os.chdir(original_cwd)

        self.assertEqual(status, 0)
        self.assertTrue(observed_summary_exists_at_prompt)
        self.assertEqual(summary["trading_mode"], "paper")
        self.assertEqual(summary["starting_total_equity"], 1100.0)
        self.assertEqual(summary["ending_total_equity"], 1110.0)
        self.assertEqual(summary["total_equity_change"], 10.0)
        self.assertEqual(summary["filled_order_count"], 1)
        self.assertEqual(summary["open_position_count"], 2)
        self.assertEqual(summary["daily_usage"]["paper_filled_notional"], 110.0)

    def test_postmarket_prompt_reads_paper_summary_path(self) -> None:
        prompt = Path("src/prompts/postmarket/summary.txt").read_text(encoding="utf-8")

        self.assertIn("PAPER_POSTMARKET_SUMMARY_PATH", prompt)
        self.assertIn("Paper Account Review", prompt)


if __name__ == "__main__":
    unittest.main()
