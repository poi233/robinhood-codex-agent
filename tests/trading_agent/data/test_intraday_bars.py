import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from trading_agent.data.intraday_bars import capture_intraday_bars, load_intraday_bars


class _Q:
    def __init__(self, price):
        self.price = price


class IntradayBarsTests(unittest.TestCase):
    def test_capture_then_load_groups_and_sorts(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture_intraday_bars(root, run_date="2026-06-24", quotes={"AAA": _Q(10.0), "BBB": _Q(20.0)}, timestamp="2026-06-24T14:00:00Z")
            capture_intraday_bars(root, run_date="2026-06-24", quotes={"AAA": _Q(10.5)}, timestamp="2026-06-24T14:05:00Z")
            bars = load_intraday_bars(root, run_date="2026-06-24")
        self.assertEqual(bars["AAA"], [("2026-06-24T14:00:00Z", 10.0), ("2026-06-24T14:05:00Z", 10.5)])
        self.assertEqual(bars["BBB"], [("2026-06-24T14:00:00Z", 20.0)])

    def test_capture_skips_nonpositive_prices(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            n = capture_intraday_bars(root, run_date="2026-06-24", quotes={"AAA": _Q(0.0), "BBB": _Q(-1.0), "CCC": _Q(5.0)}, timestamp="t")
            bars = load_intraday_bars(root, run_date="2026-06-24")
        self.assertEqual(n, 1)
        self.assertEqual(set(bars), {"CCC"})

    def test_load_empty_when_no_file(self):
        with TemporaryDirectory() as tmp:
            self.assertEqual(load_intraday_bars(Path(tmp), run_date="2026-06-24"), {})

    def test_flag_gates_capture_in_pipeline(self):
        from trading_agent.orchestration import intraday

        class _Inputs:
            quotes = {"AAA": _Q(10.0)}
            intraday_bars: dict = {}

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "runtime" / "state" / "runs" / "2026-06-24" / "intraday_bars.jsonl"
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("ENABLE_INTRADAY_BAR_CAPTURE", None)
                intraday._maybe_capture_intraday_bars(root, "2026-06-24", _Inputs())
            self.assertFalse(target.exists())  # flag off → no-op
            with mock.patch.dict(os.environ, {"ENABLE_INTRADAY_BAR_CAPTURE": "1"}, clear=False):
                intraday._maybe_capture_intraday_bars(root, "2026-06-24", _Inputs())
            self.assertTrue(target.exists())  # flag on → captured


if __name__ == "__main__":
    unittest.main()
