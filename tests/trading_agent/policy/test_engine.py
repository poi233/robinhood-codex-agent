import unittest
from datetime import datetime

from trading_agent.core.time import PT
from trading_agent.policy.engine import generate_order_intent
from trading_agent.policy.models import PolicyInputs, Quote


def base_inputs(*, trading_mode: str = "paper") -> PolicyInputs:
    fresh_timestamp = datetime.now(tz=PT).isoformat()
    return PolicyInputs(
        run_date="2026-06-14",
        trading_mode=trading_mode,
        risk_tier=0,
        risk_caps={"max_single_order_notional": 10, "max_daily_notional": 25},
        universe=["NVDA"],
        today_allowlist=["NVDA"],
        daily_plan={
            "date": "2026-06-14",
            "market_regime": "normal",
            "allowed_actions": ["small_limit_buy", "partial_take_profit"],
            "today_watchlist": ["NVDA"],
            "symbol_trade_rules": {
                "NVDA": {
                    "max_notional": 10,
                    "breakout_allowed": False,
                    "entry_condition": "price in entry zone",
                }
            },
        },
        dynamic_allowlist={
            "date": "2026-06-14",
            "symbol_scores": {
                "NVDA": {
                    "score": 85,
                    "setup": "pullback",
                    "max_notional": 10,
                }
            },
        },
        candidate_scores={
            "date": "2026-06-14",
            "symbols": {
                "NVDA": {"score": 85, "total_score": 85, "components": {"technical": 78, "catalyst": 70}}
            },
        },
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
                    "do_not_chase_above": 102.0,
                    "no_trade_low": 100.6,
                    "no_trade_high": 100.9,
                    "invalidation_below": 99.0,
                    "risk_reduction_trigger_below": 98.5,
                    "risk_reduction_target_1": 97.5,
                    "risk_reduction_target_2": 96.0,
                    "target_1": 103.0,
                    "target_2": 105.0,
                }
            }
        },
        data_status_summary={"execution_blocking": False, "reason_codes": []},
        capital_snapshot={"sizing_buying_power": 25.0},
        catalyst_snapshot={"symbols": {"NVDA": {"score": 70}}},
        policy_profile={
            "name": "aggressive_growth",
            "per_trade_risk_pct": 0.005,
            "cash_buffer_pct": 0.1,
            "pullback_score_threshold": 82,
            "breakout_score_threshold": 88,
            "technical_min_score": 70,
            "min_reward_risk": 1.5,
            "breakout_chase_tolerance_pct": 0.002,
            "minimum_trade_notional": 1.0
        },
        daily_usage={"date": "2026-06-14", "used_notional": 0},
        account={"buying_power": 25.0},
        quotes={"NVDA": Quote(symbol="NVDA", price=100.0, previous_close=101.0, timestamp=fresh_timestamp)},
        technical_signals={
            "symbols": {
                "NVDA": {
                    "long_setup": {
                        "status": "active",
                        "trigger_above": 100.5,
                        "entry_zone": {"low": 99.5, "high": 100.5},
                        "invalidation_below": 99.0,
                        "target_1": 103.0,
                        "target_2": 105.0,
                        "do_not_chase_above": 102.0,
                    },
                    "short_setup": {
                        "status": "watch",
                        "trigger_below": 98.5,
                        "target_1": 97.5,
                        "target_2": 96.0,
                    },
                    "no_trade_zone": {"low": 100.6, "high": 100.9, "reason": "range chop"},
                }
            }
        },
    )


class PolicyEngineTests(unittest.TestCase):
    def test_missing_daily_plan_blocks_decision(self) -> None:
        inputs = base_inputs()
        inputs.daily_plan = None

        decision = generate_order_intent(inputs)

        self.assertEqual(decision.decision, "blocked")
        self.assertIn("missing_daily_plan", decision.blocked_reasons)
        self.assertIsNone(decision.intent)

    def test_paper_mode_returns_would_trade_for_valid_buy_candidate(self) -> None:
        decision = generate_order_intent(base_inputs())

        self.assertEqual(decision.decision, "would_trade")
        self.assertIsNotNone(decision.intent)
        self.assertEqual(decision.intent.symbol, "NVDA")
        self.assertEqual(decision.intent.side, "buy")
        self.assertEqual(decision.action_taken, "none")

    def test_missing_account_data_blocks_decision(self) -> None:
        inputs = base_inputs()
        inputs.account = {}

        decision = generate_order_intent(inputs)

        self.assertEqual(decision.decision, "blocked")
        self.assertIn("missing_account", decision.blocked_reasons)
        self.assertIsNone(decision.intent)

    def test_kill_switch_blocks_inside_policy_engine(self) -> None:
        inputs = base_inputs()
        inputs.kill_switch_present = True
        inputs.trading_mode = "live"

        decision = generate_order_intent(inputs)

        self.assertEqual(decision.decision, "blocked")
        self.assertIn("kill_switch_present", decision.blocked_reasons)

    def test_kill_switch_does_not_block_paper_mode(self) -> None:
        inputs = base_inputs()
        inputs.kill_switch_present = True
        inputs.trading_mode = "paper"

        decision = generate_order_intent(inputs)

        self.assertEqual(decision.decision, "would_trade")
        self.assertTrue(decision.risk_checks["kill_switch"])

    def test_stale_daily_plan_blocks_decision(self) -> None:
        inputs = base_inputs()
        inputs.daily_plan["date"] = "2026-06-13"

        decision = generate_order_intent(inputs)

        self.assertEqual(decision.decision, "blocked")
        self.assertIn("stale_daily_plan", decision.blocked_reasons)

    def test_execution_blocking_data_status_blocks_decision(self) -> None:
        inputs = base_inputs()
        inputs.data_status_summary = {"execution_blocking": True, "reason_codes": ["quotes:provider_failed"]}

        decision = generate_order_intent(inputs)

        self.assertEqual(decision.decision, "blocked")
        self.assertIn("data_status_blocked", decision.blocked_reasons)

    def test_risk_overlay_no_trade_blocks_decision(self) -> None:
        inputs = base_inputs()
        inputs.risk_overlay["market_regime"] = "no_trade"

        decision = generate_order_intent(inputs)

        self.assertEqual(decision.decision, "blocked")
        self.assertIn("risk_overlay_blocks_trading", decision.blocked_reasons)

    def test_cooldown_after_buy_blocks_reentry(self) -> None:
        inputs = base_inputs()
        inputs.daily_usage = {
            "date": "2026-06-14",
            "used_notional": 0,
            "last_buy_date_by_symbol": {"NVDA": "2026-06-13"},
        }
        inputs.policy_profile["cooldown_days_after_buy"] = 3

        decision = generate_order_intent(inputs)

        self.assertEqual(decision.decision, "blocked")
        self.assertIn("cooldown_after_buy", decision.blocked_reasons)

    def test_review_mode_blocks_execution_when_unwired(self) -> None:
        decision = generate_order_intent(base_inputs(trading_mode="review"))

        self.assertEqual(decision.decision, "blocked")
        self.assertIsNotNone(decision.intent)
        self.assertIn("execution_not_wired", decision.blocked_reasons)
        self.assertEqual(decision.action_taken, "none")

    def test_deterministic_execution_makes_live_match_paper(self) -> None:
        # With deterministic_execution, review/live produce the SAME would_trade
        # decision as paper (execution is handled downstream by the execute prompt).
        paper = generate_order_intent(base_inputs())
        for mode in ("review", "live"):
            inputs = base_inputs(trading_mode=mode)
            inputs.deterministic_execution = True
            decision = generate_order_intent(inputs)
            self.assertEqual(decision.decision, "would_trade")
            self.assertIsNotNone(decision.intent)
            self.assertEqual(decision.intent.symbol, paper.intent.symbol)
            self.assertEqual(decision.intent.limit_price, paper.intent.limit_price)
            self.assertNotIn("execution_not_wired", decision.blocked_reasons)

    def test_policy_decision_serializes_to_intraday_json_shape(self) -> None:
        decision = generate_order_intent(base_inputs())

        payload = decision.to_json_dict(timestamp="2026-06-14T09:45:00-0700")

        self.assertEqual(payload["timestamp"], "2026-06-14T09:45:00-0700")
        self.assertEqual(payload["run_kind"], "intraday")
        self.assertEqual(payload["trading_mode"], "paper")
        self.assertEqual(payload["decision"], "would_trade")
        self.assertEqual(payload["action_taken"], "none")
        self.assertEqual(payload["proposed_order"]["symbol"], "NVDA")
        self.assertIsNone(payload["order_id_if_any"])


if __name__ == "__main__":
    unittest.main()
