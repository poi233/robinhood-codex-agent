from __future__ import annotations

import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from trading_agent.core.io import write_json
from trading_agent.signals.dsa_metrics import build_dsa_metrics


def _series(start_price: float, n: int, run_date: str, *, daily_change: float = 0.5) -> list[dict]:
    end = date.fromisoformat(run_date)
    rows = []
    price = start_price
    for i in range(n):
        day = end - timedelta(days=n - i)
        rows.append(
            {
                "date": day.isoformat(),
                "open": price - 0.1,
                "high": price + 0.2,
                "low": price - 0.3,
                "close": price,
                "volume": 1_000_000 + i * 500,
            }
        )
        price += daily_change
    return rows


def _fake_downloader_factory(data: dict[str, list[dict]]):
    def _downloader(tickers: list[str], lookback_days: int, run_date: str) -> dict[str, list[dict]]:
        return {sym: rows for sym, rows in data.items() if sym in tickers}

    return _downloader


class BuildDsaMetricsTests(unittest.TestCase):
    def test_basic_metrics_with_injected_downloader(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            universe = root / "universe.txt"
            meta = root / "universe_meta.json"
            universe.write_text("NVDA\nAMD\nSPY\n", encoding="utf-8")
            write_json(meta, {
                "NVDA": {"theme": "ai_semiconductor", "liquidity": 1},
                "AMD": {"theme": "ai_semiconductor", "liquidity": 1},
                "SPY": {"theme": "broad_beta", "liquidity": 1},
            })
            run_date = "2026-06-15"
            data = {
                "NVDA": _series(100.0, 90, run_date, daily_change=0.8),
                "AMD": _series(80.0, 90, run_date, daily_change=0.1),
                "SPY": _series(400.0, 90, run_date, daily_change=0.2),
            }
            downloader = _fake_downloader_factory(data)

            result = build_dsa_metrics(
                universe_file=universe,
                meta_file=meta,
                run_date=run_date,
                downloader=downloader,
            )

            self.assertEqual(result["data_status"], "ok")
            self.assertEqual(result["symbols"]["NVDA"]["theme"], "ai_semiconductor")
            self.assertEqual(result["symbols"]["NVDA"]["data_quality"], "ok")
            self.assertIn("20d", result["symbols"]["NVDA"]["rel_strength_vs_spy"])
            # NVDA rises faster than SPY -> positive relative strength
            self.assertGreater(result["symbols"]["NVDA"]["rel_strength_vs_spy"]["20d"], 0)
            self.assertIn("ai_semiconductor", result["theme_metrics"])
            self.assertEqual(result["theme_metrics"]["ai_semiconductor"]["member_count"], 2)
            self.assertIn("NVDA", result["theme_metrics"]["ai_semiconductor"]["leaders"])

    def test_missing_symbol_marked_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            universe = root / "universe.txt"
            meta = root / "universe_meta.json"
            universe.write_text("NVDA\nGHOST\nSPY\n", encoding="utf-8")
            write_json(meta, {"NVDA": {"theme": "ai_semiconductor", "liquidity": 1}, "SPY": {"theme": "broad_beta", "liquidity": 1}})
            run_date = "2026-06-15"
            data = {
                "NVDA": _series(100.0, 90, run_date),
                "SPY": _series(400.0, 90, run_date),
            }
            downloader = _fake_downloader_factory(data)

            result = build_dsa_metrics(universe, meta, run_date, downloader=downloader)

            self.assertEqual(result["symbols"]["GHOST"]["data_quality"], "failed")
            self.assertEqual(result["data_status"], "partial")

    def test_market_breadth_computed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            universe = root / "universe.txt"
            meta = root / "universe_meta.json"
            universe.write_text("NVDA\nAMD\nSPY\n", encoding="utf-8")
            write_json(meta, {})
            run_date = "2026-06-15"
            data = {
                "NVDA": _series(100.0, 90, run_date, daily_change=0.8),
                "AMD": _series(80.0, 90, run_date, daily_change=0.1),
                "SPY": _series(400.0, 90, run_date, daily_change=0.2),
            }
            downloader = _fake_downloader_factory(data)

            result = build_dsa_metrics(universe, meta, run_date, downloader=downloader)

            self.assertIsNotNone(result["market_breadth"]["pct_above_sma50"])

    def test_all_symbols_missing_returns_failed_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            universe = root / "universe.txt"
            meta = root / "universe_meta.json"
            universe.write_text("NVDA\n", encoding="utf-8")
            write_json(meta, {})

            result = build_dsa_metrics(universe, meta, "2026-06-15", downloader=lambda t, l, r: {})

            self.assertEqual(result["data_status"], "failed")
            self.assertEqual(result["symbols"]["NVDA"]["data_quality"], "failed")

    def test_mock_mode_without_explicit_downloader(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            universe = root / "universe.txt"
            meta = root / "universe_meta.json"
            universe.write_text("NVDA\nSPY\n", encoding="utf-8")
            write_json(meta, {})

            result = build_dsa_metrics(universe, meta, "2026-06-15", mock=True)

            self.assertEqual(result["data_status"], "ok")
            self.assertEqual(result["symbols"]["NVDA"]["data_quality"], "ok")


if __name__ == "__main__":
    unittest.main()
