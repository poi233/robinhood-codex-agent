import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "kronos_generate_signals.py"
RUNNER_PATH = REPO_ROOT / "scripts" / "run_kronos_premarket_scan.sh"


class CommonRuntimeTests(unittest.TestCase):
    def test_common_sh_prefers_runtime_env_local(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            config_dir = tmp / "config"
            scripts_dir = tmp / "scripts"
            config_dir.mkdir()
            scripts_dir.mkdir()

            (config_dir / "runtime.env").write_text("TRADING_MODE=paper\n", encoding="utf-8")
            (config_dir / "runtime.env.local").write_text("TRADING_MODE=review\n", encoding="utf-8")
            (scripts_dir / "common.sh").write_text((REPO_ROOT / "scripts" / "common.sh").read_text(encoding="utf-8"), encoding="utf-8")

            result = subprocess.run(
                ["bash", "-lc", f"cd {tmp} && source scripts/common.sh && printf '%s' \"$TRADING_MODE\""],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "review")

    def test_common_sh_exports_fallback_kronos_paths_to_child_processes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            config_dir = tmp / "config"
            scripts_dir = tmp / "scripts"
            config_dir.mkdir()
            scripts_dir.mkdir()

            (config_dir / "runtime.env").write_text("TRADING_MODE=paper\n", encoding="utf-8")
            (scripts_dir / "common.sh").write_text((REPO_ROOT / "scripts" / "common.sh").read_text(encoding="utf-8"), encoding="utf-8")

            result = subprocess.run(
                [
                    "bash",
                    "-lc",
                    (
                        f"cd {tmp} && source scripts/common.sh && "
                        "python3 -c 'import os; "
                        "print(os.environ[\"KRONOS_PYTHON_BIN\"]); "
                        "print(os.environ[\"KRONOS_PROJECT_ROOT\"])'"
                    ),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertEqual(
                result.stdout,
                f"{tmp / '.venv-kronos' / 'bin' / 'python'}\n{tmp / '.vendor' / 'kronos'}\n",
            )

    def test_common_sh_prefers_explicit_shell_env_over_env_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            config_dir = tmp / "config"
            scripts_dir = tmp / "scripts"
            config_dir.mkdir()
            scripts_dir.mkdir()

            (config_dir / "runtime.env").write_text("TRADING_MODE=paper\n", encoding="utf-8")
            (config_dir / "runtime.env.local").write_text("TRADING_MODE=review\n", encoding="utf-8")
            (scripts_dir / "common.sh").write_text((REPO_ROOT / "scripts" / "common.sh").read_text(encoding="utf-8"), encoding="utf-8")

            env = dict(**os.environ, TRADING_MODE="live")
            result = subprocess.run(
                ["bash", "-lc", f"cd {tmp} && source scripts/common.sh && printf '%s' \"$TRADING_MODE\""],
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )

            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "live")


class PortableArtifactTests(unittest.TestCase):
    def test_runtime_env_local_example_exists(self) -> None:
        self.assertTrue((REPO_ROOT / "config" / "runtime.env.local.example").exists())

    def test_requirements_kronos_extra_exists(self) -> None:
        self.assertTrue((REPO_ROOT / "requirements-kronos-extra.txt").exists())

    def test_setup_and_verify_scripts_exist(self) -> None:
        self.assertTrue((REPO_ROOT / "scripts" / "setup_kronos_env.sh").exists())
        self.assertTrue((REPO_ROOT / "scripts" / "verify_kronos_env.sh").exists())

    def test_verify_script_skips_task3_generation_until_script_exists(self) -> None:
        contents = (REPO_ROOT / "scripts" / "verify_kronos_env.sh").read_text(encoding="utf-8")

        self.assertIn('if [[ -f "$AGENT_ROOT/scripts/kronos_generate_signals.py" ]]; then', contents)
        self.assertIn("pending Task 3", contents)

    def test_verify_script_uses_temp_output_and_cleans_it_up(self) -> None:
        contents = (REPO_ROOT / "scripts" / "verify_kronos_env.sh").read_text(encoding="utf-8")

        self.assertIn("mktemp", contents)
        self.assertIn("trap", contents)
        self.assertNotIn('state/kronos_signals.json', contents)

    def test_setup_doc_does_not_claim_task3_scripts_exist_yet(self) -> None:
        contents = (REPO_ROOT / "docs" / "setup" / "kronos-portable-setup.md").read_text(encoding="utf-8")

        self.assertIn("Python `venv` support", contents)
        self.assertIn("pending later tasks", contents)
        self.assertNotIn("run_kronos_premarket_scan.sh", contents)


class KronosGenerateSignalsTests(unittest.TestCase):
    def test_generate_mock_signals_writes_expected_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            universe = tmp / "universe.txt"
            output = tmp / "kronos_signals.json"
            universe.write_text("NVDA\nPLTR\n# comment\nNVDA\n", encoding="utf-8")

            cmd = [
                sys.executable,
                str(SCRIPT_PATH),
                "--universe-file",
                str(universe),
                "--output-file",
                str(output),
                "--date",
                "2026-06-13",
                "--mock",
            ]
            subprocess.run(cmd, check=True, cwd=REPO_ROOT)

            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["date"], "2026-06-13")
            self.assertEqual(payload["timeframe"], "30m")
            self.assertEqual(payload["horizon_bars"], 8)
            self.assertEqual(sorted(payload["symbols"].keys()), ["NVDA", "PLTR"])
            self.assertEqual(payload["model"]["mode"], "inference_only_mock")

    def test_rejects_predictions_for_symbols_outside_universe(self) -> None:
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        import kronos_generate_signals as mod

        with self.assertRaises(ValueError):
            mod.validate_signal_symbols({"NVDA"}, {"TSLA": {}})


class KronosRunnerTests(unittest.TestCase):
    def test_mock_runner_writes_repo_state_file(self) -> None:
        state_file = REPO_ROOT / "state" / "kronos_signals.json"
        if state_file.exists():
            state_file.unlink()

        env = os.environ.copy()
        env.update(
            {
                "ALLOW_WEEKEND_RUN": "1",
                "KRONOS_USE_MOCK": "1",
                "KRONOS_PYTHON_BIN": sys.executable,
            }
        )
        subprocess.run(["bash", str(RUNNER_PATH)], check=True, cwd=REPO_ROOT, env=env)

        payload = json.loads(state_file.read_text(encoding="utf-8"))
        self.assertIn("symbols", payload)
        self.assertIn("generated_at", payload)
