import tempfile
import unittest
from pathlib import Path

from trading_agent.core.context import RuntimePaths, build_runtime_paths
from trading_agent.core.time import pt_date_string


class CoreRuntimeTests(unittest.TestCase):
    def test_pt_date_string_shape(self) -> None:
        value = pt_date_string()
        self.assertRegex(value, r"^\d{4}-\d{2}-\d{2}$")

    def test_build_runtime_paths_uses_repo_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            paths = build_runtime_paths(root)
            self.assertEqual(paths.agent_root, root)
            self.assertEqual(paths.state_dir, root / "runtime" / "state")
            self.assertEqual(paths.reports_dir, root / "runtime" / "reports")
            self.assertEqual(paths.daily_plan_zh_markdown_path, root / "runtime" / "state" / "runs" / paths.run_date / "planner" / "daily_plan.zh.md")
            self.assertEqual(paths.premarket_diagnostics_path, root / "runtime" / "state" / "runs" / paths.run_date / "planner" / "premarket_diagnostics.json")
            self.assertEqual(paths.paper_account_path, root / "runtime" / "state" / "runs" / paths.run_date / "paper" / "account.json")
            self.assertEqual(paths.paper_positions_path, root / "runtime" / "state" / "runs" / paths.run_date / "paper" / "positions.json")
            self.assertEqual(paths.paper_postmarket_summary_path, root / "runtime" / "state" / "runs" / paths.run_date / "paper" / "postmarket_summary.json")
            self.assertEqual(paths.decisions_log_path, root / "runtime" / "logs" / "runs" / paths.run_date / "audit" / "decisions.jsonl")
            self.assertEqual(paths.codex_run_log_path, root / "runtime" / "logs" / "runs" / paths.run_date / "outputs" / "codex_runs.log")
            self.assertEqual(paths.error_log_path, root / "runtime" / "logs" / "runs" / paths.run_date / "system" / "errors.log")
            self.assertEqual(paths.postmarket_summary_path, root / "runtime" / "logs" / "runs" / paths.run_date / "reports" / "postmarket_summary.md")

    def test_runtime_paths_are_dataclass_like(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            paths = build_runtime_paths(root)
            self.assertIsInstance(paths, RuntimePaths)
