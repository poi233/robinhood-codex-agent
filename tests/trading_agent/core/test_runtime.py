import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from trading_agent.core.config import RuntimeConfig, TierMisconfigurationError, load_env_files
from trading_agent.core.context import RuntimePaths, build_runtime_paths, resolve_agent_root
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

    def test_resolve_agent_root_prefers_current_working_repo_root_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "src" / "config").mkdir(parents=True)
            (root / "src" / "trading_agent").mkdir(parents=True)
            (root / "src" / "config" / "runtime.env").write_text("", encoding="utf-8")
            with mock.patch("trading_agent.core.context.Path.cwd", return_value=root):
                self.assertEqual(resolve_agent_root(), root)

    def test_resolve_agent_root_falls_back_when_cwd_is_not_repo_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cwd = Path(tmpdir)
            with mock.patch("trading_agent.core.context.Path.cwd", return_value=cwd):
                resolved = resolve_agent_root()
                self.assertTrue((resolved / "src" / "trading_agent").exists())
                self.assertTrue((resolved / "src" / "config").exists())

    def test_runtime_paths_are_dataclass_like(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            paths = build_runtime_paths(root)
            self.assertIsInstance(paths, RuntimePaths)

    def test_load_env_files_applies_local_override_not_already_in_environ(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "src" / "config").mkdir(parents=True)
            (root / "src" / "config" / "runtime.env").write_text("FOO=base\n", encoding="utf-8")
            (root / "src" / "config" / "runtime.env.local").write_text("FOO=local\n", encoding="utf-8")

            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("FOO", None)
                load_env_files(root)
                self.assertEqual(os.environ["FOO"], "local")

    def test_load_env_files_never_overrides_existing_shell_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "src" / "config").mkdir(parents=True)
            (root / "src" / "config" / "runtime.env").write_text("FOO=base\n", encoding="utf-8")
            (root / "src" / "config" / "runtime.env.local").write_text("FOO=local\n", encoding="utf-8")

            with mock.patch.dict(os.environ, {"FOO": "shell"}, clear=False):
                load_env_files(root)
                self.assertEqual(os.environ["FOO"], "shell")

    def test_load_env_files_is_a_noop_when_config_files_are_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            load_env_files(root)

    def test_load_env_files_backfills_risk_tier_from_strategy_registry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "src" / "config").mkdir(parents=True)
            (root / "src" / "config" / "strategy_registry.yaml").write_text(
                "active_strategy: experimental_v2\n"
                "strategies:\n"
                "  experimental_v2:\n"
                "    scoring_profile: conservative\n"
                "    policy_profile: conservative\n"
                "    risk_tier_paper: 2\n"
                "    risk_tier_live: 1\n"
                "    change_reason: \"test\"\n",
                encoding="utf-8",
            )

            with mock.patch.dict(os.environ, {}, clear=False):
                for key in ("SCORING_PROFILE", "POLICY_PROFILE", "RISK_TIER", "PAPER_RISK_TIER"):
                    os.environ.pop(key, None)
                load_env_files(root)
                self.assertEqual(os.environ["SCORING_PROFILE"], "conservative")
                self.assertEqual(os.environ["RISK_TIER"], "1")
                self.assertEqual(os.environ["PAPER_RISK_TIER"], "2")

    def test_load_env_files_lets_runtime_env_local_override_strategy_registry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "src" / "config").mkdir(parents=True)
            (root / "src" / "config" / "strategy_registry.yaml").write_text(
                "active_strategy: experimental_v2\n"
                "strategies:\n"
                "  experimental_v2:\n"
                "    risk_tier_live: 1\n"
                "    risk_tier_paper: 2\n"
                "    change_reason: \"test\"\n",
                encoding="utf-8",
            )
            (root / "src" / "config" / "runtime.env.local").write_text("RISK_TIER=0\n", encoding="utf-8")

            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("RISK_TIER", None)
                load_env_files(root)
                self.assertEqual(os.environ["RISK_TIER"], "0")

    def test_effective_risk_tier_fails_closed_for_live_mode_at_tier_4(self) -> None:
        config = RuntimeConfig(
            trading_mode="live",
            codex_model="gpt-5.4",
            codex_model_mini="gpt-5.4",
            risk_tier=4,
            paper_risk_tier=4,
            market_feed_timeframes="1d",
        )
        with self.assertRaises(TierMisconfigurationError):
            config.effective_risk_tier

    def test_effective_risk_tier_fails_closed_for_review_mode_at_tier_4(self) -> None:
        config = RuntimeConfig(
            trading_mode="review",
            codex_model="gpt-5.4",
            codex_model_mini="gpt-5.4",
            risk_tier=4,
            paper_risk_tier=0,
            market_feed_timeframes="1d",
        )
        with self.assertRaises(TierMisconfigurationError):
            config.effective_risk_tier

    def test_effective_risk_tier_allows_tier_4_in_paper_mode(self) -> None:
        config = RuntimeConfig(
            trading_mode="paper",
            codex_model="gpt-5.4",
            codex_model_mini="gpt-5.4",
            risk_tier=0,
            paper_risk_tier=4,
            market_feed_timeframes="1d",
        )
        self.assertEqual(config.effective_risk_tier, 4)

    def test_effective_risk_tier_allows_live_mode_below_tier_4(self) -> None:
        config = RuntimeConfig(
            trading_mode="live",
            codex_model="gpt-5.4",
            codex_model_mini="gpt-5.4",
            risk_tier=2,
            paper_risk_tier=4,
            market_feed_timeframes="1d",
        )
        self.assertEqual(config.effective_risk_tier, 2)
