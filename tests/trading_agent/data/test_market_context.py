import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from trading_agent.data import market_context
from trading_agent.data.market_context import (
    _prefetch_ohlcv_batch,
    collect_market_context,
)


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

    def test_batch_prefetch_used_when_no_cache(self) -> None:
        """D2: when cache_dir is None and not mock, batch fetch is used instead of per-symbol."""
        fake_rows = [{"timestamp": "2026-06-14T00:00:00+00:00", "open": 1, "high": 2, "low": 1, "close": 2, "volume": 10}]
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            universe = root / "universe.txt"
            universe.write_text("NVDA\n", encoding="utf-8")
            output = root / "market_feed"
            with mock.patch(
                "trading_agent.data.market_context.fetch_live_rows_batch",
                return_value={"NVDA": fake_rows},
            ) as batch_mock, mock.patch.object(
                market_context, "build_live_news_payload",
                return_value={
                    "symbol": "NVDA", "date": "2026-06-14", "headlines": [],
                    "news": {"status": "ok", "error": ""},
                    "earnings": {"status": "ok", "calendar": {}},
                    "filings": {"status": "ok", "items": [], "error": ""},
                },
            ):
                result = collect_market_context(
                    universe_file=universe, output_dir=output, run_date="2026-06-14",
                    timeframes=["1d"], news_limit=2, mock=False, cache_dir=None,
                )
            batch_mock.assert_called()
            self.assertEqual(result["data_status"], "ok")

    def test_batch_fetch_disabled_falls_back_to_per_symbol(self) -> None:
        """D2: when ENABLE_BATCH_OHLCV_FETCH=0, per-symbol fetch_live_rows is used."""
        fake_rows = [{"timestamp": "2026-06-14T00:00:00+00:00", "open": 1, "high": 2, "low": 1, "close": 2, "volume": 10}]
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            universe = root / "universe.txt"
            universe.write_text("NVDA\n", encoding="utf-8")
            output = root / "market_feed"
            with mock.patch.dict(os.environ, {"ENABLE_BATCH_OHLCV_FETCH": "0"}, clear=False), \
                 mock.patch.object(market_context, "fetch_live_rows", return_value=fake_rows) as per_sym_mock, \
                 mock.patch.object(
                     market_context, "build_live_news_payload",
                     return_value={
                         "symbol": "NVDA", "date": "2026-06-14", "headlines": [],
                         "news": {"status": "ok", "error": ""},
                         "earnings": {"status": "ok", "calendar": {}},
                         "filings": {"status": "ok", "items": [], "error": ""},
                     },
                 ):
                result = collect_market_context(
                    universe_file=universe, output_dir=output, run_date="2026-06-14",
                    timeframes=["1d"], news_limit=2, mock=False, cache_dir=None,
                )
            per_sym_mock.assert_called()
            self.assertEqual(result["data_status"], "ok")

    def test_batch_fetch_failure_falls_back_to_per_symbol(self) -> None:
        """D2: if batch fetch raises, _process_one_symbol falls back to per-symbol fetch_live_rows."""
        fake_rows = [{"timestamp": "2026-06-14T00:00:00+00:00", "open": 1, "high": 2, "low": 1, "close": 2, "volume": 10}]
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            universe = root / "universe.txt"
            universe.write_text("NVDA\n", encoding="utf-8")
            output = root / "market_feed"
            with mock.patch(
                "trading_agent.data.market_context.fetch_live_rows_batch",
                side_effect=RuntimeError("network error"),
            ), mock.patch.object(
                market_context, "fetch_live_rows", return_value=fake_rows
            ) as per_sym_mock, mock.patch.object(
                market_context, "build_live_news_payload",
                return_value={
                    "symbol": "NVDA", "date": "2026-06-14", "headlines": [],
                    "news": {"status": "ok", "error": ""},
                    "earnings": {"status": "ok", "calendar": {}},
                    "filings": {"status": "ok", "items": [], "error": ""},
                },
            ):
                result = collect_market_context(
                    universe_file=universe, output_dir=output, run_date="2026-06-14",
                    timeframes=["1d"], news_limit=2, mock=False, cache_dir=None,
                )
            per_sym_mock.assert_called()
            self.assertEqual(result["data_status"], "ok")

    def test_prefetch_ohlcv_batch_returns_none_when_disabled(self) -> None:
        with mock.patch.dict(os.environ, {"ENABLE_BATCH_OHLCV_FETCH": "0"}, clear=False):
            result = _prefetch_ohlcv_batch(["NVDA"], ["1d"])
        self.assertIsNone(result)

    def test_prefetch_ohlcv_batch_returns_none_on_exception(self) -> None:
        with mock.patch(
            "trading_agent.data.market_context.fetch_live_rows_batch",
            side_effect=RuntimeError("boom"),
        ):
            result = _prefetch_ohlcv_batch(["NVDA"], ["1d"])
        self.assertIsNone(result)
