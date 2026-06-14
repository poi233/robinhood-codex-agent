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
