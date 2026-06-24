"""Tests for the pluggable buy-side setups + the decide_buy_price dispatcher.

Covers: each alternative setup fires on the geometry it is meant for and blocks otherwise; the
champion (default setups) blocks the same inputs the alternatives would trade; the dispatcher
defaults to pullback+breakout and skips unknown names; and an engine-level end-to-end where a
challenger profile produces a buy on a symbol the champion is structurally silent on.
"""

import unittest
from datetime import datetime
from pathlib import Path

from trading_agent.core.time import PT
from trading_agent.policy.candidate_selector import RankedCandidate
from trading_agent.policy.engine import generate_order_intent
from trading_agent.policy.models import PolicyInputs, Quote
from trading_agent.policy.price_policy import decide_buy_price
from trading_agent.policy.profiles import load_policy_profile

REPO_ROOT = Path(__file__).resolve().parents[3]

# A champion-style profile with NO `setups` key → dispatcher falls back to pullback+breakout.
CHAMPION_PROFILE = {
    "name": "aggressive_growth_mid",
    "pullback_score_threshold": 82,
    "breakout_score_threshold": 88,
    "technical_min_score": 70,
    "min_reward_risk": 1.5,
    "breakout_chase_tolerance_pct": 0.002,
    "per_trade_risk_pct": 0.005,
    "minimum_trade_notional": 1.0,
}


def _quote(price: float) -> Quote:
    return Quote(symbol="ABC", price=price, previous_close=price, timestamp=datetime.now(tz=PT).isoformat())


def _inputs(*, price: float, profile, watch: dict, score: float = 70.0, technical: float = 70.0,
            research_bias: str | None = None) -> PolicyInputs:
    research = {"ABC": {"research_bias": research_bias}} if research_bias else {}
    return PolicyInputs(
        run_date="2026-06-23",
        trading_mode="paper",
        risk_tier=0,
        risk_caps={"max_single_order_notional": 10000, "max_daily_notional": 40000},
        universe=["ABC"],
        today_allowlist=["ABC"],
        daily_plan={
            "date": "2026-06-23",
            "market_regime": "normal",
            "allowed_actions": ["small_limit_buy"],
            "today_watchlist": ["ABC"],
            "symbol_trade_rules": {"ABC": {"allow_buy": True}},
        },
        candidate_scores={"date": "2026-06-23", "symbols": {"ABC": {"total_score": score, "components": {"technical": technical}}}},
        risk_overlay={"symbol_trade_rules": {"ABC": {"allow_buy": True}}},
        trader_watch_levels={"symbols": {"ABC": watch}},
        data_status_summary={"execution_blocking": False},
        capital_snapshot={"sizing_buying_power": 10000.0},
        catalyst_snapshot={"symbols": {"ABC": {"score": 60}}},
        policy_profile=profile,
        daily_usage={},
        research_reports=research,
        technical_signals={"symbols": {"ABC": {"setup": "none"}}},
        account={"buying_power": 10000.0},
        quotes={"ABC": _quote(price)},
    )


def _candidate(score: float = 70.0, technical: float = 70.0) -> RankedCandidate:
    return RankedCandidate("ABC", score, score, technical, 70.0, 70.0, 80.0)


# A "non-bullish premarket" symbol: champion fields collapsed (zero-width entry zone, no-trade zone
# covering the whole range, do_not_chase at resistance) but real key_levels are present.
def _non_bullish_watch(**overrides) -> dict:
    watch = {
        "reference_price": 100.0,
        "range_low": 90.0,
        "range_high": 120.0,
        "supports": [95.0],
        "resistances": [105.0, 115.0],
        # champion-facing fields (collapsed for a non-bullish symbol)
        "entry_low": 100.0,
        "entry_high": 100.0,
        "buy_trigger_above": 105.0,
        "do_not_chase_above": 105.0,
        "no_trade_low": 95.0,
        "no_trade_high": 105.0,
        "invalidation_below": 94.8,
        "target_1": 105.0,
        "target_2": 115.0,
        "long_status": "watch",
    }
    watch.update(overrides)
    return watch


class MomentumBreakoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = load_policy_profile(REPO_ROOT, profile_name="momentum_breakout")

    def test_fires_just_above_resistance(self) -> None:
        inputs = _inputs(price=105.5, profile=self.profile, watch=_non_bullish_watch())
        decision = decide_buy_price(inputs, _candidate())
        self.assertIsNone(decision.blocked_reason)
        self.assertEqual(decision.setup_type, "breakout_momentum")
        self.assertGreaterEqual(decision.reward_risk or 0, self.profile["min_reward_risk"])
        # stop sits just below the broken level, not way down at support.
        self.assertGreater(decision.stop_price, 100.0)

    def test_blocks_below_trigger(self) -> None:
        inputs = _inputs(price=104.0, profile=self.profile, watch=_non_bullish_watch())
        decision = decide_buy_price(inputs, _candidate())
        self.assertEqual(decision.blocked_reason, "below_breakout_trigger")

    def test_blocks_when_chasing_too_far(self) -> None:
        inputs = _inputs(price=110.0, profile=self.profile, watch=_non_bullish_watch())
        decision = decide_buy_price(inputs, _candidate())
        self.assertEqual(decision.blocked_reason, "breakout_chase_tolerance_blocked")


class TrendContinuationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = load_policy_profile(REPO_ROOT, profile_name="trend_follow")

    def test_fires_above_reference_with_nearby_support(self) -> None:
        inputs = _inputs(price=102.0, profile=self.profile, watch=_non_bullish_watch(supports=[100.5, 96.0]))
        decision = decide_buy_price(inputs, _candidate())
        self.assertIsNone(decision.blocked_reason)
        self.assertEqual(decision.setup_type, "trend_continuation")
        self.assertGreaterEqual(decision.reward_risk or 0, self.profile["min_reward_risk"])

    def test_blocks_when_extended(self) -> None:
        inputs = _inputs(price=106.0, profile=self.profile, watch=_non_bullish_watch(supports=[100.5]))
        decision = decide_buy_price(inputs, _candidate())
        self.assertEqual(decision.blocked_reason, "trend_extended")

    def test_blocks_on_bearish_research_bias(self) -> None:
        inputs = _inputs(price=102.0, profile=self.profile, watch=_non_bullish_watch(supports=[100.5]),
                         research_bias="avoid")
        decision = decide_buy_price(inputs, _candidate())
        self.assertEqual(decision.blocked_reason, "research_bias_blocks_trend")


class DipPullbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = load_policy_profile(REPO_ROOT, profile_name="dip_pullback")

    def test_fires_in_band_above_support(self) -> None:
        watch = _non_bullish_watch(supports=[100.0], resistances=[110.0, 120.0])
        inputs = _inputs(price=102.0, profile=self.profile, watch=watch)
        decision = decide_buy_price(inputs, _candidate())
        self.assertIsNone(decision.blocked_reason)
        self.assertEqual(decision.setup_type, "dip_pullback")
        self.assertLess(decision.stop_price, 102.0)

    def test_blocks_below_support(self) -> None:
        watch = _non_bullish_watch(supports=[100.0])
        inputs = _inputs(price=99.5, profile=self.profile, watch=watch)
        decision = decide_buy_price(inputs, _candidate())
        self.assertEqual(decision.blocked_reason, "below_support")

    def test_blocks_outside_dip_band(self) -> None:
        watch = _non_bullish_watch(supports=[100.0])
        inputs = _inputs(price=104.0, profile=self.profile, watch=watch)  # >100*1.03
        decision = decide_buy_price(inputs, _candidate())
        self.assertEqual(decision.blocked_reason, "outside_dip_band")


class RangeReversionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = load_policy_profile(REPO_ROOT, profile_name="range_reversion")

    def test_fires_near_range_low(self) -> None:
        inputs = _inputs(price=92.0, profile=self.profile, watch=_non_bullish_watch())
        decision = decide_buy_price(inputs, _candidate())
        self.assertIsNone(decision.blocked_reason)
        self.assertEqual(decision.setup_type, "range_reversion")
        self.assertLess(decision.stop_price, 90.0)  # below the range floor

    def test_blocks_above_buy_zone(self) -> None:
        inputs = _inputs(price=108.0, profile=self.profile, watch=_non_bullish_watch())
        decision = decide_buy_price(inputs, _candidate())
        self.assertEqual(decision.blocked_reason, "above_range_buy_zone")

    def test_blocks_outside_range(self) -> None:
        inputs = _inputs(price=125.0, profile=self.profile, watch=_non_bullish_watch())
        decision = decide_buy_price(inputs, _candidate())
        self.assertEqual(decision.blocked_reason, "outside_range")


class ChampionVsAlternativesTests(unittest.TestCase):
    def test_champion_blocks_the_prices_alternatives_trade(self) -> None:
        # At each alternative's entry price, the champion (default setups) refuses to trade.
        for price in (92.0, 102.0, 105.5):
            inputs = _inputs(price=price, profile=CHAMPION_PROFILE, watch=_non_bullish_watch(supports=[100.5]))
            decision = decide_buy_price(inputs, _candidate())
            self.assertIsNotNone(decision.blocked_reason, f"champion unexpectedly traded at {price}")


class DispatcherTests(unittest.TestCase):
    def test_defaults_to_pullback_breakout_when_no_setups_key(self) -> None:
        # Price inside a real (bullish-style) entry zone with a high score → champion pullback fires.
        watch = {
            "entry_low": 99.5, "entry_high": 100.5, "buy_trigger_above": 100.5,
            "do_not_chase_above": 101.0, "no_trade_low": None, "no_trade_high": None,
            "invalidation_below": 99.0, "target_1": 103.0, "target_2": 105.0,
        }
        inputs = _inputs(price=100.0, profile=CHAMPION_PROFILE, watch=watch, score=85, technical=78)
        decision = decide_buy_price(inputs, _candidate(score=85, technical=78))
        self.assertIsNone(decision.blocked_reason)
        self.assertEqual(decision.setup_type, "pullback")

    def test_unknown_setup_name_falls_through(self) -> None:
        profile = {"setups": ["does_not_exist"], "min_reward_risk": 1.5}
        inputs = _inputs(price=92.0, profile=profile, watch=_non_bullish_watch())
        decision = decide_buy_price(inputs, _candidate())
        self.assertEqual(decision.blocked_reason, "no_setup_configured")


class EngineEndToEndTests(unittest.TestCase):
    def test_challenger_buys_where_champion_is_silent(self) -> None:
        watch = _non_bullish_watch()
        champion_decision = generate_order_intent(
            _inputs(price=92.0, profile=CHAMPION_PROFILE, watch=watch)
        )
        self.assertIn(champion_decision.decision, {"blocked", "no_action"})
        self.assertIsNone(champion_decision.intent)

        range_profile = load_policy_profile(REPO_ROOT, profile_name="range_reversion")
        challenger_decision = generate_order_intent(
            _inputs(price=92.0, profile=range_profile, watch=watch)
        )
        self.assertEqual(challenger_decision.decision, "would_trade")
        self.assertIsNotNone(challenger_decision.intent)
        self.assertEqual(challenger_decision.intent.setup_type, "range_reversion")


def _with_prev_close(inputs: PolicyInputs, price: float, prev_close: float) -> PolicyInputs:
    inputs.quotes["ABC"] = Quote(symbol="ABC", price=price, previous_close=prev_close, timestamp=datetime.now(tz=PT).isoformat())
    return inputs


class GapFillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = load_policy_profile(REPO_ROOT, profile_name="gap_fill")

    def test_fires_on_gap_down_and_targets_prior_close(self) -> None:
        inputs = _with_prev_close(_inputs(price=96.0, profile=self.profile, watch=_non_bullish_watch()), 96.0, 100.0)
        decision = decide_buy_price(inputs, _candidate())
        self.assertIsNone(decision.blocked_reason)
        self.assertEqual(decision.setup_type, "gap_fill")
        self.assertEqual(decision.target_1, 100.0)  # gap-fill target = prior close
        self.assertGreaterEqual(decision.reward_risk or 0, self.profile["min_reward_risk"])

    def test_blocks_when_gap_too_small(self) -> None:
        inputs = _with_prev_close(_inputs(price=99.5, profile=self.profile, watch=_non_bullish_watch()), 99.5, 100.0)
        self.assertEqual(decide_buy_price(inputs, _candidate()).blocked_reason, "gap_too_small")

    def test_blocks_when_gap_too_large(self) -> None:
        inputs = _with_prev_close(_inputs(price=80.0, profile=self.profile, watch=_non_bullish_watch()), 80.0, 100.0)
        self.assertEqual(decide_buy_price(inputs, _candidate()).blocked_reason, "gap_too_large")


class FailedBreakdownTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = load_policy_profile(REPO_ROOT, profile_name="failed_breakdown")

    def test_fires_on_reclaim_after_close_below_support(self) -> None:
        # support_1 = max(supports) = 95; prior close 93 (below), price 96 reclaimed within band.
        inputs = _with_prev_close(_inputs(price=96.0, profile=self.profile, watch=_non_bullish_watch()), 96.0, 93.0)
        decision = decide_buy_price(inputs, _candidate())
        self.assertIsNone(decision.blocked_reason)
        self.assertEqual(decision.setup_type, "failed_breakdown")
        self.assertLess(decision.stop_price, 95.0)  # stop sits below the trap, under support

    def test_blocks_when_no_breakdown(self) -> None:
        inputs = _with_prev_close(_inputs(price=96.0, profile=self.profile, watch=_non_bullish_watch()), 96.0, 96.0)
        self.assertEqual(decide_buy_price(inputs, _candidate()).blocked_reason, "no_breakdown_to_reclaim")

    def test_blocks_when_reclaim_extended(self) -> None:
        inputs = _with_prev_close(_inputs(price=99.0, profile=self.profile, watch=_non_bullish_watch()), 99.0, 93.0)
        self.assertEqual(decide_buy_price(inputs, _candidate()).blocked_reason, "reclaim_extended")


class BreakoutRetestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = load_policy_profile(REPO_ROOT, profile_name="breakout_retest")

    def test_fires_on_retest_of_broken_resistance(self) -> None:
        # resistance 105: prior close 107 cleared it, price 106 pulled back to retest within band.
        inputs = _with_prev_close(_inputs(price=106.0, profile=self.profile, watch=_non_bullish_watch()), 106.0, 107.0)
        decision = decide_buy_price(inputs, _candidate())
        self.assertIsNone(decision.blocked_reason)
        self.assertEqual(decision.setup_type, "breakout_retest")
        self.assertGreater(decision.stop_price, 103.0)  # stop just below the retested 105 level
        self.assertEqual(decision.target_1, 115.0)  # next resistance above the broken level

    def test_blocks_when_prior_close_did_not_break_out(self) -> None:
        inputs = _with_prev_close(_inputs(price=106.0, profile=self.profile, watch=_non_bullish_watch()), 106.0, 104.0)
        self.assertEqual(decide_buy_price(inputs, _candidate()).blocked_reason, "no_retest")


if __name__ == "__main__":
    unittest.main()
