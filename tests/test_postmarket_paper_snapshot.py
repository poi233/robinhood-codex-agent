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
            paper_dir = root / "state" / "runs" / "2026-06-14" / "paper"
            paper_dir.mkdir(parents=True)
            (root / "config").mkdir()
            (root / "config" / "runtime.env").write_text("TRADING_MODE=paper\n", encoding="utf-8")
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
                    mock.patch.object(postmarket_module, "pt_date_string", return_value="2026-06-14"), \
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


if __name__ == "__main__":
    unittest.main()
