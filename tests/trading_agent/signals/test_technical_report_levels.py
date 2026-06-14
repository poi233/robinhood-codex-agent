import unittest
import tempfile
import json
from pathlib import Path

from trading_agent.reporting.premarket import build_fail_closed_daily_plan, build_premarket_archive_payload
from trading_agent.signals.technical_fallback import build_failed_technical_payload


class TechnicalReportLevelTests(unittest.TestCase):
    def test_archive_payload_includes_trader_watch_levels(self) -> None:
        technical_payload = {
            "date": "2026-06-14",
            "symbols": {
                "NVDA": {
                    "technical_action": "observe",
                    "confidence": 0.7,
                    "key_levels": {"prior_close": 100},
                    "long_setup": {"trigger_above": 101, "entry_zone": {"low": 99, "high": 100}},
                    "short_setup": {"trigger_below": 95},
                    "no_trade_zone": {"low": 100, "high": 101, "reason": "range"},
                }
            },
        }
        payload = build_premarket_archive_payload(
            run_date="2026-06-14",
            daily_plan={"date": "2026-06-14", "today_watchlist": ["NVDA"]},
            technical_payload=technical_payload,
        )
        self.assertIn("trader_watch_levels", payload)
        self.assertIn("NVDA", payload["trader_watch_levels"]["symbols"])

    def test_build_fail_closed_daily_plan_marks_no_trade(self) -> None:
        payload = build_fail_closed_daily_plan("2026-06-14", "planner missing")
        self.assertEqual(payload["market_regime"], "no_trade")
        self.assertEqual(payload["allowed_actions"], [])
        self.assertIn("planner missing", payload["no_trade_reasons"])

    def test_failed_technical_payload_preserves_reference_prices_from_daily_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            ohlcv_root = root / "ohlcv"
            (ohlcv_root / "NVDA").mkdir(parents=True)
            (ohlcv_root / "NVDA" / "daily.json").write_text(
                json.dumps(
                    [
                        {"low": 96.0, "high": 101.0, "close": 100.0},
                        {"low": 98.0, "high": 105.0, "close": 103.5},
                    ]
                ),
                encoding="utf-8",
            )
            manifest = {
                "requested_symbols": ["NVDA"],
                "artifacts": {"ohlcv_root": str(ohlcv_root)},
            }

            payload = build_failed_technical_payload(
                manifest,
                run_date="2026-06-14",
                reason="technical prompt failed",
            )

            nvda = payload["symbols"]["NVDA"]
            self.assertEqual(nvda["key_levels"]["reference_price"], 103.5)
            self.assertIn(96.0, nvda["key_levels"]["supports"])
            self.assertIn(105.0, nvda["key_levels"]["resistances"])
