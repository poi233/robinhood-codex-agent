import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from trading_agent.data import market_context
from trading_agent.data.market_context import collect_market_context


class MarketContextTests(unittest.TestCase):
    def test_collect_market_context_mock_mode_writes_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            universe = root / "universe.txt"
            output = root / "market_feed"
            universe.write_text("NVDA\nSPY\n", encoding="utf-8")

            result = collect_market_context(
                universe_file=universe,
                output_dir=output,
                run_date="2026-06-14",
                timeframes=["1d"],
                news_limit=2,
                mock=True,
            )

            self.assertEqual(result["data_status"], "ok")
            self.assertTrue((output / "manifest.json").exists())

    def test_collect_market_context_clears_stale_artifacts_before_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            universe = root / "universe.txt"
            output = root / "market_feed"
            universe.write_text("NVDA\n", encoding="utf-8")

            stale = output / "ohlcv" / "OLD" / "daily.json"
            stale.parent.mkdir(parents=True, exist_ok=True)
            stale.write_text("[]\n", encoding="utf-8")

            collect_market_context(
                universe_file=universe,
                output_dir=output,
                run_date="2026-06-14",
                timeframes=["1d"],
                news_limit=2,
                mock=True,
            )

            self.assertFalse(stale.exists())
            self.assertTrue((output / "ohlcv" / "NVDA" / "daily.json").exists())

    def test_live_mode_keeps_symbol_complete_when_news_is_partial(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            universe = root / "universe.txt"
            output = root / "market_feed"
            universe.write_text("NVDA\n", encoding="utf-8")

            with mock.patch.object(
                market_context,
                "fetch_live_rows",
                return_value=[{"timestamp": "2026-06-14T00:00:00+00:00", "open": 1, "high": 2, "low": 1, "close": 2, "volume": 10}],
            ), mock.patch.object(
                market_context,
                "build_live_news_payload",
                return_value={
                    "symbol": "NVDA",
                    "date": "2026-06-14",
                    "headlines": [],
                    "news": {"status": "failed", "error": "403"},
                    "earnings": {"status": "ok", "calendar": {}},
                    "filings": {"status": "ok", "items": [], "error": ""},
                },
            ):
                result = collect_market_context(
                    universe_file=universe,
                    output_dir=output,
                    run_date="2026-06-14",
                    timeframes=["1d"],
                    news_limit=2,
                    mock=False,
                )

            self.assertEqual(result["data_status"], "partial")
            self.assertEqual(result["completed_symbols"], ["NVDA"])
            self.assertEqual(result["failed_symbols"], [])
            self.assertEqual(result["symbol_status"]["NVDA"]["news"], "failed")

    def test_live_mode_uses_ohlcv_cache_when_cache_dir_is_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            universe = root / "universe.txt"
            output = root / "market_feed"
            cache_dir = root / "cache" / "ohlcv"
            universe.write_text("NVDA\n", encoding="utf-8")

            with mock.patch(
                "trading_agent.data.ohlcv_cache.fetch_cached_rows",
                return_value=[{"timestamp": "2026-06-14T00:00:00+00:00", "open": 1, "high": 2, "low": 1, "close": 2, "volume": 10}],
            ) as fetch_cached, mock.patch.object(
                market_context,
                "build_live_news_payload",
                return_value={
                    "symbol": "NVDA",
                    "date": "2026-06-14",
                    "headlines": [],
                    "news": {"status": "ok", "error": ""},
                    "earnings": {"status": "ok", "calendar": {}},
                    "filings": {"status": "ok", "items": [], "error": ""},
                },
            ):
                result = collect_market_context(
                    universe_file=universe,
                    output_dir=output,
                    run_date="2026-06-14",
                    timeframes=["1d"],
                    news_limit=2,
                    mock=False,
                    cache_dir=cache_dir,
                )

            fetch_cached.assert_called_once_with("NVDA", "1d", date(2026, 6, 14), cache_dir)
            self.assertEqual(result["data_status"], "ok")
