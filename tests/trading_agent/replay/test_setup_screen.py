import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from trading_agent.core.time import PT
from trading_agent.policy.models import PolicyInputs, Quote
from trading_agent.replay import setup_screen
from trading_agent.replay.setup_screen import (
    HypotheticalFill,
    _evaluate_fills,
    screen_all_setups,
    screen_setups,
)


def _inputs_for(run_date: str, symbol: str, price: float, *, candidate_score: float = 80.0) -> PolicyInputs:
    """A point-in-time PolicyInputs crafted so trend_continuation + range_reversion fire and the
    champion/momentum/dip setups block (range_low=95, support=95, resistance=110, range_high=120,
    reference=100, price=100). Mirrors the fields rank_candidates + the setups actually read."""
    watch = {
        "supports": [95.0],
        "resistances": [110.0],
        "range_low": 95.0,
        "range_high": 120.0,
        "reference_price": 100.0,
    }
    return PolicyInputs(
        run_date=run_date,
        trading_mode="paper",
        risk_tier=0,
        risk_caps={"max_single_order_notional": 1000, "max_daily_notional": 5000},
        universe=[symbol],
        today_allowlist=[symbol],
        daily_plan={
            "date": run_date,
            "market_regime": "normal",
            "allowed_actions": ["small_limit_buy"],
            "today_watchlist": [symbol],
            "symbol_trade_rules": {symbol: {"max_notional": 1000}},
        },
        candidate_scores={
            "date": run_date,
            "symbols": {symbol: {"total_score": candidate_score, "components": {"technical": 78}}},
        },
        risk_overlay={"date": run_date, "symbol_trade_rules": {symbol: {"allow_buy": True}}},
        trader_watch_levels={"symbols": {symbol: watch}},
        data_status_summary={"execution_blocking": False, "reason_codes": []},
        catalyst_snapshot={"symbols": {symbol: {"score": 65}}},
        policy_profile={"name": "test", "min_reward_risk": 1.5},
        account={"buying_power": 100000.0},
        quotes={symbol: Quote(symbol=symbol, price=price, previous_close=price, timestamp=datetime.now(tz=PT).isoformat())},
        technical_signals={"symbols": {symbol: {"long_setup": {"status": "watch"}}}},
    )


def _stub_loader(series: dict[str, list[tuple[str, float]]]):
    def loader(symbol: str, start: str, end: str) -> list[tuple[str, float]]:
        return series.get(symbol, [])

    return loader


# AAA rises through the 110 target; BBB falls through the trend/range stops.
_AAA_BARS = [("2026-06-10", 100.0), ("2026-06-11", 105.0), ("2026-06-12", 111.0),
             ("2026-06-13", 112.0), ("2026-06-14", 113.0), ("2026-06-15", 114.0), ("2026-06-16", 115.0)]
_BBB_BARS = [("2026-06-11", 100.0), ("2026-06-12", 98.0), ("2026-06-13", 96.0),
             ("2026-06-14", 93.0), ("2026-06-15", 92.0), ("2026-06-16", 90.0)]


class EvaluateFillsTests(unittest.TestCase):
    def test_target_first_stop_first_and_forward_return(self) -> None:
        fills = [
            HypotheticalFill("2026-06-10", "AAA", "trend_continuation", 100.0, 97.0, 110.0, 3.3),
            HypotheticalFill("2026-06-11", "BBB", "trend_continuation", 100.0, 97.0, 110.0, 3.3),
        ]
        agg = _evaluate_fills(fills, lookahead=5, price_loader=_stub_loader({"AAA": _AAA_BARS, "BBB": _BBB_BARS}))
        row = agg["trend_continuation"]
        self.assertEqual(row["fills"], 2)
        self.assertEqual(row["target_first"], 1)  # AAA hit 110
        self.assertEqual(row["stop_first"], 1)  # BBB hit 97
        # forward return at the 5d horizon: AAA 114/100-1=+0.14, BBB 90/100-1=-0.10
        self.assertAlmostEqual(row["fwd"][0], 0.14, places=6)
        self.assertAlmostEqual(row["fwd"][1], -0.10, places=6)

    def test_missing_levels_or_bars_count_as_undecided(self) -> None:
        fills = [
            HypotheticalFill("2026-06-10", "AAA", "x", 100.0, None, 110.0, None),  # no stop
            HypotheticalFill("2026-06-10", "ZZZ", "x", 100.0, 97.0, 110.0, 3.3),  # no bars
        ]
        agg = _evaluate_fills(fills, lookahead=5, price_loader=_stub_loader({"AAA": _AAA_BARS}))
        self.assertEqual(agg["x"]["undecided"], 2)
        self.assertEqual(agg["x"]["target_first"], 0)


class ScreenSetupsTests(unittest.TestCase):
    def _run(self, fn, **kwargs):
        loader = _stub_loader({"AAA": _AAA_BARS, "BBB": _BBB_BARS})
        inputs_by_date = {"2026-06-10": _inputs_for("2026-06-10", "AAA", 100.0),
                          "2026-06-11": _inputs_for("2026-06-11", "BBB", 100.0)}

        def fake_load(agent_root, *, run_date, **_kw):
            return inputs_by_date[run_date]

        with mock.patch.object(setup_screen, "discover_run_dates", return_value=["2026-06-10", "2026-06-11"]), \
            mock.patch.object(setup_screen, "load_policy_inputs", side_effect=fake_load):
            return fn(Path("/unused"), price_loader=loader, **kwargs)

    def test_screen_specific_setup_attributes_and_scores(self) -> None:
        report = self._run(screen_setups, setups=["trend_continuation"])
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["fills"], 2)
        self.assertEqual(len(report["rows"]), 1)
        row = report["rows"][0]
        self.assertEqual(row["setup_type"], "trend_continuation")
        self.assertEqual(row["fills"], 2)
        self.assertEqual(row["win_rate"], 0.5)  # 1 target / (1 target + 1 stop)

    def test_screen_all_setups_is_head_to_head_per_setup(self) -> None:
        report = self._run(screen_all_setups)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["mode"], "per_setup")
        fired = {row["setup_type"] for row in report["rows"]}
        # The crafted fixture makes exactly these two challenger setups fire.
        self.assertIn("trend_continuation", fired)
        self.assertIn("range_reversion", fired)
        # Champion pullback/breakout (no entry zone provided) and momentum/dip stay silent.
        self.assertNotIn("pullback", fired)
        self.assertNotIn("breakout", fired)
        for row in report["rows"]:
            self.assertEqual(row["fills"], 2)
            self.assertEqual(row["win_rate"], 0.5)

    def test_no_data_returns_no_data_status(self) -> None:
        with mock.patch.object(setup_screen, "discover_run_dates", return_value=[]):
            report = screen_all_setups(Path("/unused"), price_loader=_stub_loader({}))
        self.assertEqual(report["status"], "no_data")
        self.assertEqual(report["rows"], [])


if __name__ == "__main__":
    unittest.main()
