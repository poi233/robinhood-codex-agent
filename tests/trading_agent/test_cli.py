import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


class PackageCliTests(unittest.TestCase):
    def test_python_module_help_exits_zero(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "trading_agent", "--help"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            env={**__import__("os").environ, "PYTHONPATH": str(REPO_ROOT / "src")},
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("premarket", result.stdout)
        self.assertIn("intraday", result.stdout)
        self.assertIn("postmarket", result.stdout)

    def test_parser_accepts_runtime_subcommands(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "trading_agent", "premarket", "--help"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            env={**__import__("os").environ, "PYTHONPATH": str(REPO_ROOT / "src")},
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("--dry-run", result.stdout)

    def test_doctor_command_prints_effective_config(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "trading_agent", "doctor"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            env={**__import__("os").environ, "PYTHONPATH": str(REPO_ROOT / "src")},
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("TRADING_MODE", result.stdout)
        self.assertIn("PAPER_RISK_TIER", result.stdout)
        self.assertIn("effective_risk_tier", result.stdout)
        self.assertIn("active_strategy", result.stdout)
        self.assertIn("baseline_v1", result.stdout)

    def test_doctor_respects_env_override(self) -> None:
        import os
        env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src"), "TRADING_MODE": "review", "RISK_TIER": "2"}
        result = subprocess.run(
            [sys.executable, "-m", "trading_agent", "doctor"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("TRADING_MODE              = review", result.stdout)
        self.assertIn("effective_risk_tier now   = 2", result.stdout)

    def test_doctor_fails_closed_when_live_mode_has_tier_4(self) -> None:
        import os
        env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src"), "TRADING_MODE": "live", "RISK_TIER": "4"}
        result = subprocess.run(
            [sys.executable, "-m", "trading_agent", "doctor"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        self.assertEqual(result.returncode, 2, msg=result.stderr)
        self.assertIn("FAIL-CLOSED", result.stdout)

    def test_analytics_build_command_runs_and_reports_row_counts(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "trading_agent", "analytics", "build"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            env={**__import__("os").environ, "PYTHONPATH": str(REPO_ROOT / "src")},
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("analytics.db", result.stdout)
        self.assertIn("runs", result.stdout)
        self.assertIn("candidates", result.stdout)
        (REPO_ROOT / "runtime" / "analytics" / "analytics.db").unlink(missing_ok=True)

    def test_doctor_does_not_fail_closed_in_paper_mode_at_tier_4(self) -> None:
        import os
        env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src"), "TRADING_MODE": "paper", "PAPER_RISK_TIER": "4"}
        result = subprocess.run(
            [sys.executable, "-m", "trading_agent", "doctor"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("effective_risk_tier now   = 4", result.stdout)
