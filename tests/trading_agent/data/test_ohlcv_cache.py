from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from trading_agent.core.io import read_json
from trading_agent.data import ohlcv_cache
from trading_agent.data.ohlcv_cache import cache_path, fetch_cached_rows


def _row(ts: str, close: float) -> dict:
    return {"timestamp": ts, "open": close - 1, "high": close + 1, "low": close - 1, "close": close, "volume": 1000}


class OhlcvCacheTests(unittest.TestCase):
    def test_no_cache_does_full_fetch_and_writes_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            full_rows = [_row("2026-06-01T00:00:00", 100.0), _row("2026-06-02T00:00:00", 101.0)]

            with mock.patch.object(ohlcv_cache, "fetch_live_rows", return_value=full_rows) as fetch:
                rows = fetch_cached_rows("NVDA", "1d", date(2026, 6, 15), cache_dir)

            fetch.assert_called_once_with("NVDA", "1d")
            self.assertEqual(rows, full_rows)
            saved = read_json(cache_path(cache_dir, "NVDA", "1d"))
            self.assertEqual(saved["rows"], full_rows)

    def test_existing_cache_does_incremental_fetch_and_merges(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            path = cache_path(cache_dir, "NVDA", "1d")
            cached_rows = [_row("2026-06-10T00:00:00", 100.0), _row("2026-06-11T00:00:00", 101.0)]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(__import__("json").dumps({"symbol": "NVDA", "timeframe": "1d", "rows": cached_rows}), encoding="utf-8")

            incremental_rows = [_row("2026-06-11T00:00:00", 101.0), _row("2026-06-12T00:00:00", 102.0)]

            with mock.patch.object(ohlcv_cache, "fetch_live_rows", return_value=incremental_rows) as fetch:
                rows = fetch_cached_rows("NVDA", "1d", date(2026, 6, 15), cache_dir)

            fetch.assert_called_once_with("NVDA", "1d", period="5d")
            timestamps = [row["timestamp"] for row in rows]
            self.assertEqual(timestamps, ["2026-06-10T00:00:00", "2026-06-11T00:00:00", "2026-06-12T00:00:00"])

    def test_diverging_close_prices_triggers_full_refetch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            path = cache_path(cache_dir, "NVDA", "1d")
            cached_rows = [_row("2026-06-10T00:00:00", 100.0)]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(__import__("json").dumps({"symbol": "NVDA", "timeframe": "1d", "rows": cached_rows}), encoding="utf-8")

            # Same timestamp, very different close => looks like a split/dividend adjustment.
            diverged_incremental = [_row("2026-06-10T00:00:00", 50.0)]
            full_refetch_rows = [_row("2026-06-10T00:00:00", 50.0), _row("2026-06-14T00:00:00", 52.0)]

            with mock.patch.object(
                ohlcv_cache, "fetch_live_rows", side_effect=[diverged_incremental, full_refetch_rows]
            ) as fetch:
                rows = fetch_cached_rows("NVDA", "1d", date(2026, 6, 15), cache_dir)

            self.assertEqual(fetch.call_args_list[0], mock.call("NVDA", "1d", period="5d"))
            self.assertEqual(fetch.call_args_list[1], mock.call("NVDA", "1d"))
            self.assertEqual(rows, full_refetch_rows)

    def test_intraday_timeframes_are_never_cached(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            with mock.patch.object(ohlcv_cache, "fetch_live_rows", return_value=[]) as fetch:
                fetch_cached_rows("NVDA", "15m", date(2026, 6, 15), cache_dir)

            fetch.assert_called_once_with("NVDA", "15m")
            self.assertFalse(cache_path(cache_dir, "NVDA", "15m").exists())

    def test_merge_trims_rows_outside_the_lookback_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            path = cache_path(cache_dir, "NVDA", "1d")
            old_row = _row("2020-01-01T00:00:00", 10.0)
            recent_row = _row("2026-06-10T00:00:00", 100.0)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                __import__("json").dumps({"symbol": "NVDA", "timeframe": "1d", "rows": [old_row, recent_row]}),
                encoding="utf-8",
            )

            with mock.patch.object(ohlcv_cache, "fetch_live_rows", return_value=[recent_row]):
                rows = fetch_cached_rows("NVDA", "1d", date(2026, 6, 15), cache_dir)

            timestamps = [row["timestamp"] for row in rows]
            self.assertNotIn("2020-01-01T00:00:00", timestamps)
            self.assertIn("2026-06-10T00:00:00", timestamps)


if __name__ == "__main__":
    unittest.main()
