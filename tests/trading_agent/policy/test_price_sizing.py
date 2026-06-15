import unittest
from datetime import datetime

from trading_agent.policy.candidate_selector import RankedCandidate
from trading_agent.policy.models import Position
from trading_agent.policy.models import PolicyInputs, Quote
from trading_agent.policy.price_policy import decide_buy_price
from trading_agent.policy.sizing_policy import decide_size
from trading_agent.core.time import PT


def base_inputs() -> PolicyInputs:
    fresh_timestamp = datetime.now(tz=PT).isoformat()
    return PolicyInputs(
        run_date="2026-06-14",
        trading_mode="paper",
        risk_tier=0,
        risk_caps={"max_single_order_notional": 10, "max_daily_notional": 25},
        universe=["NVDA"],
        today_allowlist=["NVDA"],
        daily_plan={
            "date": "2026-06-14",
            "market_regime": "normal",
            "allowed_actions": ["small_limit_buy"],
            "today_watchlist": ["NVDA"],
            "symbol_trade_rules": {"NVDA": {"max_notional": 10, "breakout_allowed": True}},
        },
        candidate_scores={"date": "2026-06-14", "symbols": {"NVDA": {"total_score": 85}}},
        dynamic_allowlist={"date": "2026-06-14", "symbol_scores": {"NVDA": {"theme": "ai_semis"}}},
        risk_overlay={
            "date": "2026-06-14",
            "market_regime": "aggressive_ok",
            "max_single_order_notional": 10,
            "max_daily_notional": 25,
            "symbol_trade_rules": {"NVDA": {"max_notional": 10, "allow_buy": True}},
        },
        trader_watch_levels={
            "symbols": {
                "NVDA": {
                    "entry_low": 99.5,
                    "entry_high": 100.5,
                    "buy_trigger_above": 100.5,
                    "do_not_chase_above": 100.6,
                    "no_trade_low": 100.6,
                    "no_trade_high": 100.9,
                    "invalidation_below": 99.0,
                    "target_1": 103.0,
                    "target_2": 105.0,
                }
            }
        },
        data_status_summary={"execution_blocking": False, "reason_codes": []},
        capital_snapshot={"sizing_buying_power": 25.0},
        catalyst_snapshot={"date": "2026-06-14", "symbols": {"NVDA": {"score": 70}}},
        policy_profile={
            "name": "aggressive_growth",
            "per_trade_risk_pct": 0.005,
            "cash_buffer_pct": 0.1,
            "pullback_score_threshold": 82,
            "breakout_score_threshold": 88,
            "technical_min_score": 70,
            "min_reward_risk": 1.5,
            "breakout_chase_tolerance_pct": 0.002,
            "max_theme_weight": 0.5,
            "minimum_trade_notional": 1.0
        },
        daily_usage={"date": "2026-06-14", "used_notional": 0},
        account={"buying_power": 25.0},
        quotes={"NVDA": Quote(symbol="NVDA", price=100.0, previous_close=101.0, timestamp=fresh_timestamp)},
    )


class PriceSizingPolicyTests(unittest.TestCase):
    def test_pullback_entry_ok(self) -> None:
        inputs = base_inputs()
        candidate = RankedCandidate("NVDA", 85, 82, 78, 80, 70, 80)

        decision = decide_buy_price(inputs, candidate)

        self.assertEqual(decision.setup_type, "pullback")
        self.assertIsNone(decision.blocked_reason)
        self.assertGreater(decision.reward_risk or 0, 1.5)

    def test_no_trade_zone_blocked(self) -> None:
        inputs = base_inputs()
        inputs.quotes["NVDA"] = Quote(symbol="NVDA", price=100.7, previous_close=101.0, timestamp="2026-06-14T09:45:00-07:00")
        candidate = RankedCandidate("NVDA", 85, 82, 78, 80, 70, 80)

        decision = decide_buy_price(inputs, candidate)

        self.assertEqual(decision.blocked_reason, "no_trade_zone")

    def test_breakout_chase_tolerance_blocked(self) -> None:
        inputs = base_inputs()
        inputs.quotes["NVDA"] = Quote(symbol="NVDA", price=100.8, previous_close=101.0, timestamp="2026-06-14T09:45:00-07:00")
        inputs.trader_watch_levels["symbols"]["NVDA"]["entry_low"] = 95.0
        inputs.trader_watch_levels["symbols"]["NVDA"]["entry_high"] = 99.0
        inputs.trader_watch_levels["symbols"]["NVDA"]["no_trade_low"] = 101.1
        inputs.trader_watch_levels["symbols"]["NVDA"]["no_trade_high"] = 101.2
        candidate = RankedCandidate("NVDA", 90, 88, 78, 80, 70, 80)

        decision = decide_buy_price(inputs, candidate)

        self.assertEqual(decision.blocked_reason, "chase_blocked")

    def test_size_reduced_by_profile_multipliers(self) -> None:
        inputs = base_inputs()
        candidate = RankedCandidate("NVDA", 85, 82, 78, 60, 70, 80)
        price = decide_buy_price(inputs, candidate)

        decision = decide_size(inputs, candidate, price)

        self.assertGreater(decision.quantity, 0)
        self.assertLess(decision.estimated_notional, 10.0)
        self.assertIsNone(decision.blocked_reason)

    def test_size_is_capped_by_theme_weight(self) -> None:
        inputs = base_inputs()
        inputs.account = {"buying_power": 20.0}
        inputs.policy_profile["minimum_trade_notional"] = 1.0
        inputs.positions = {
            "SMH": Position(symbol="SMH", quantity=0.1, average_cost=100.0, market_price=100.0),
        }
        inputs.dynamic_allowlist["symbol_scores"]["NVDA"]["theme"] = "ai_semis"
        inputs.dynamic_allowlist["symbol_scores"]["SMH"] = {"theme": "ai_semis"}
        candidate = RankedCandidate("NVDA", 93, 90, 78, 80, 70, 80)
        price = decide_buy_price(inputs, candidate)

        decision = decide_size(inputs, candidate, price)

        self.assertGreater(decision.quantity, 0)
        self.assertLessEqual(decision.estimated_notional, 5.0)
        self.assertIn("theme_weight_ok", decision.reason_codes)


if __name__ == "__main__":
    unittest.main()
