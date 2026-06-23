import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


class TechnicalPromptWiringTests(unittest.TestCase):
    def test_technical_prompt_exists_and_references_repo_skills(self) -> None:
        prompt = (REPO_ROOT / "src" / "prompts" / "technical" / "research.txt").read_text(encoding="utf-8")
        self.assertIn(".agents/skills/chan-structure-trading", prompt)
        self.assertIn(".agents/skills/brooks-trading-range-price-action", prompt)
        self.assertIn("TECHNICAL_SIGNALS_PATH", prompt)
        self.assertIn("MARKET_FEED_DIR", prompt)
        self.assertIn("TECHNICAL_MAX_SUBAGENTS", prompt)

    def test_sample_schema_contains_dual_execution_scenarios(self) -> None:
        payload = {
            "symbols": {
                "NVDA": {
                    "long_setup": {"trigger_above": 0, "entry_zone": {"low": 0, "high": 0}},
                    "short_setup": {"trigger_below": 0, "entry_zone": {"low": 0, "high": 0}},
                    "no_trade_zone": {"low": 0, "high": 0, "reason": "range"},
                }
            }
        }
        self.assertIn("long_setup", payload["symbols"]["NVDA"])
        self.assertIn("short_setup", payload["symbols"]["NVDA"])
        self.assertIn("no_trade_zone", payload["symbols"]["NVDA"])

    def test_premarket_prompt_reads_technical_signals(self) -> None:
        prompt = (REPO_ROOT / "src" / "prompts" / "premarket" / "final_research.txt").read_text(encoding="utf-8")
        self.assertIn("TECHNICAL_SIGNALS_PATH", prompt)
        self.assertIn("technical_action", prompt)

