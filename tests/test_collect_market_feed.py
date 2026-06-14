import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
COLLECTOR = REPO_ROOT / "scripts" / "collect_market_feed.py"


class MarketFeedCollectorTests(unittest.TestCase):
    def test_mock_mode_writes_manifest_and_symbol_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            universe = tmp / "universe.txt"
            output_dir = tmp / "market_feed"
            universe.write_text("NVDA\nSPY\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(COLLECTOR),
                    "--universe-file",
                    str(universe),
                    "--output-dir",
                    str(output_dir),
                    "--date",
                    "2026-06-13",
                    "--mock",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["data_status"], "ok")
            self.assertEqual(sorted(manifest["completed_symbols"]), ["NVDA", "SPY"])
            self.assertTrue((output_dir / "ohlcv" / "NVDA" / "daily.json").exists())
            self.assertTrue((output_dir / "charts" / "SPY" / "daily.png").exists())
            self.assertTrue((output_dir / "news" / "market_summary.json").exists())

    def test_run_symbol_research_script_exists(self) -> None:
        self.assertTrue((REPO_ROOT / "scripts" / "run_symbol_research.sh").exists())

    def test_runner_uses_mock_collection_in_dry_run_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "config").mkdir()
            (tmp / "scripts").mkdir()
            (tmp / "state").mkdir()
            (tmp / "logs").mkdir()
            (tmp / "config" / "runtime.env").write_text("TRADING_MODE=paper\n", encoding="utf-8")
            (tmp / "config" / "universe.txt").write_text("NVDA\n", encoding="utf-8")
            (tmp / "scripts" / "common.sh").write_text(
                (REPO_ROOT / "scripts" / "common.sh").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (tmp / "scripts" / "run_market_feed_collection.sh").write_text(
                (REPO_ROOT / "scripts" / "run_market_feed_collection.sh").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (tmp / "scripts" / "collect_market_feed.py").write_text(
                COLLECTOR.read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            result = subprocess.run(
                ["bash", "scripts/run_market_feed_collection.sh"],
                cwd=tmp,
                env={**os.environ, "CODEX_EXEC_DRY_RUN": "1"},
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            manifests = list((tmp / "state" / "market_feed").glob("*/manifest.json"))
            self.assertEqual(len(manifests), 1)

    @unittest.skipUnless(os.environ.get("RUN_LIVE_MARKET_FEED_TEST") == "1", "set RUN_LIVE_MARKET_FEED_TEST=1 to hit live market data")
    def test_live_mode_fetches_real_yfinance_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            universe = tmp / "universe.txt"
            output_dir = tmp / "market_feed_live"
            universe.write_text("NVDA\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(COLLECTOR),
                    "--universe-file",
                    str(universe),
                    "--output-dir",
                    str(output_dir),
                    "--date",
                    "2026-06-13",
                    "--timeframes",
                    "1d",
                    "--news-limit",
                    "3",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["sources"]["ohlcv"], "yfinance")
            self.assertEqual(manifest["sources"]["news"], "yfinance")
            self.assertEqual(manifest["data_status"], "ok")

            rows = json.loads((output_dir / "ohlcv" / "NVDA" / "daily.json").read_text(encoding="utf-8"))
            self.assertGreater(len(rows), 0)
            self.assertGreater(float(rows[-1]["close"]), 0.0)

            news = json.loads((output_dir / "news" / "NVDA.json").read_text(encoding="utf-8"))
            self.assertGreater(len(news["headlines"]), 0)
            self.assertNotIn("Mock catalyst", news["headlines"][0]["title"])
            self.assertIn(news["filings"]["status"], {"ok", "failed"})
