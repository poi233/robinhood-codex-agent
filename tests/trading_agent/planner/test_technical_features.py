from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from trading_agent.core.io import write_json
from trading_agent.planner.technical_features import (
    atr,
    build_technical_features,
    detect_flags,
    ema,
    find_swing_points,
    macd,
    pct_return,
    rsi,
    sma,
    trend_label,
)


def _rows(closes: list[float], *, start_volume: int = 1_000_000) -> list[dict]:
    rows = []
    for i, close in enumerate(closes):
        rows.append(
            {
                "timestamp": f"2026-01-{i + 1:02d}T00:00:00+00:00",
                "open": close - 0.2,
                "high": close + 0.3,
                "low": close - 0.4,
                "close": close,
                "volume": start_volume + i * 1000,
            }
        )
    return rows


class IndicatorMathTests(unittest.TestCase):
    def test_sma_known_sequence(self) -> None:
        closes = [1, 2, 3, 4, 5]
        self.assertEqual(sma(closes, 5), 3.0)
        self.assertIsNone(sma(closes, 6))

    def test_ema_known_sequence(self) -> None:
        closes = [float(x) for x in range(1, 11)]
        result = ema(closes, 5)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 8.04, places=1)

    def test_rsi_all_gains_is_100(self) -> None:
        closes = [float(x) for x in range(1, 20)]
        self.assertEqual(rsi(closes, 14), 100.0)

    def test_rsi_all_losses_is_0(self) -> None:
        closes = [float(x) for x in range(20, 1, -1)]
        self.assertEqual(rsi(closes, 14), 0.0)

    def test_rsi_insufficient_data_returns_none(self) -> None:
        self.assertIsNone(rsi([1.0, 2.0, 3.0], 14))

    def test_macd_insufficient_data_returns_none(self) -> None:
        self.assertIsNone(macd([float(x) for x in range(10)]))

    def test_macd_with_enough_data(self) -> None:
        closes = [100.0 + i * 0.5 for i in range(60)]
        result = macd(closes)
        self.assertIsNotNone(result)
        self.assertIn("macd", result)
        self.assertIn("signal", result)
        self.assertIn("hist", result)

    def test_atr_known_sequence(self) -> None:
        highs = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0, 21.0, 22.0, 23.0, 24.0]
        lows = [9.0, 10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0, 21.0, 22.0, 23.0]
        closes = [9.5, 10.5, 11.5, 12.5, 13.5, 14.5, 15.5, 16.5, 17.5, 18.5, 19.5, 20.5, 21.5, 22.5, 23.5]
        result = atr(highs, lows, closes, 14)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 1.5, places=1)

    def test_atr_insufficient_data_returns_none(self) -> None:
        self.assertIsNone(atr([10.0, 11.0], [9.0, 10.0], [9.5, 10.5], 14))

    def test_find_swing_points(self) -> None:
        highs = [1, 2, 5, 2, 1, 1, 2, 6, 2, 1]
        lows = [0, 1, 3, 1, 0, 0, 1, 4, 1, 0]
        result = find_swing_points([float(h) for h in highs], [float(l) for l in lows])
        self.assertIn(5.0, result["swing_highs"])
        self.assertIn(6.0, result["swing_highs"])

    def test_pct_return(self) -> None:
        closes = [100.0, 102.0, 105.0, 110.0]
        self.assertAlmostEqual(pct_return(closes, 1), 4.7619, places=3)
        self.assertIsNone(pct_return(closes, 10))

    def test_trend_label_up(self) -> None:
        self.assertEqual(trend_label(110.0, 105.0, 100.0), "up")

    def test_trend_label_down(self) -> None:
        self.assertEqual(trend_label(90.0, 95.0, 100.0), "down")

    def test_trend_label_sideways_with_no_smas(self) -> None:
        self.assertEqual(trend_label(100.0, None, None), "sideways")

    def test_detect_flags_inside_bar(self) -> None:
        rows = [
            {"open": 10.0, "high": 12.0, "low": 8.0, "close": 11.0},
            {"open": 10.5, "high": 11.5, "low": 9.0, "close": 10.8},
        ]
        flags = detect_flags(rows, sma20=None)
        self.assertIn("inside_bar", flags)

    def test_detect_flags_gap_up(self) -> None:
        rows = [
            {"open": 10.0, "high": 12.0, "low": 8.0, "close": 11.0},
            {"open": 11.5, "high": 12.5, "low": 11.0, "close": 12.0},
        ]
        flags = detect_flags(rows, sma20=None)
        self.assertIn("gap_up", flags)


class BuildTechnicalFeaturesTests(unittest.TestCase):
    def test_full_pipeline_writes_expected_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            market_feed_dir = Path(tmpdir) / "market_feed"
            closes_nvda = [100.0 + i * 0.5 for i in range(60)]
            closes_spy = [400.0 + i * 0.2 for i in range(60)]
            write_json(market_feed_dir / "ohlcv" / "NVDA" / "daily.json", _rows(closes_nvda))
            write_json(market_feed_dir / "ohlcv" / "SPY" / "daily.json", _rows(closes_spy))

            result = build_technical_features(
                market_feed_dir, ["NVDA", "SPY"], "2026-06-15", recent_bars=10, benchmark="SPY"
            )

            self.assertEqual(result["date"], "2026-06-15")
            self.assertEqual(result["recent_bars_count"], 10)
            nvda = result["symbols"]["NVDA"]
            self.assertEqual(nvda["data_quality"], "partial")  # only daily timeframe present
            daily = nvda["timeframes"]["daily"]
            self.assertIn("rsi_14", daily)
            self.assertIn("sma", daily)
            self.assertEqual(len(daily["recent_bars"]), 10)
            self.assertIn("rel_strength_vs_spy", nvda["multi_timeframe"])
            self.assertIn("5d", nvda["multi_timeframe"]["rel_strength_vs_spy"])

    def test_missing_symbol_data_is_marked_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            market_feed_dir = Path(tmpdir) / "market_feed"
            market_feed_dir.mkdir(parents=True, exist_ok=True)

            result = build_technical_features(market_feed_dir, ["NOPE"], "2026-06-15")

            self.assertEqual(result["symbols"]["NOPE"]["data_quality"], "failed")
            self.assertEqual(result["symbols"]["NOPE"]["timeframes"], {})

    def test_weekly_timeframe_has_no_recent_bars(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            market_feed_dir = Path(tmpdir) / "market_feed"
            closes = [50.0 + i * 0.3 for i in range(60)]
            write_json(market_feed_dir / "ohlcv" / "AMD" / "weekly.json", _rows(closes))

            result = build_technical_features(market_feed_dir, ["AMD"], "2026-06-15")

            weekly = result["symbols"]["AMD"]["timeframes"]["weekly"]
            self.assertNotIn("recent_bars", weekly)

    def test_full_timeframes_marks_ok_quality(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            market_feed_dir = Path(tmpdir) / "market_feed"
            closes = [50.0 + i * 0.3 for i in range(60)]
            for label in ["daily", "weekly", "hourly", "intraday_15m"]:
                write_json(market_feed_dir / "ohlcv" / "AMD" / f"{label}.json", _rows(closes))

            result = build_technical_features(market_feed_dir, ["AMD"], "2026-06-15")

            self.assertEqual(result["symbols"]["AMD"]["data_quality"], "ok")


if __name__ == "__main__":
    unittest.main()
