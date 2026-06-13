import contextlib
import io
import importlib
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

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


class PromptWiringTests(unittest.TestCase):
    def test_premarket_prompt_mentions_kronos_signal_file(self) -> None:
        prompt = (REPO_ROOT / "prompts" / "premarket_research.txt").read_text(encoding="utf-8")
        self.assertIn("state/kronos_signals.json", prompt)
        self.assertIn("kronos_signal_status", prompt)


class KronosGenerateSignalsTests(unittest.TestCase):
    @staticmethod
    def import_module():
        scripts_path = str(REPO_ROOT / "scripts")
        if scripts_path not in sys.path:
            sys.path.insert(0, scripts_path)
        if "kronos_generate_signals" in sys.modules:
            return importlib.reload(sys.modules["kronos_generate_signals"])
        return importlib.import_module("kronos_generate_signals")

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
        mod = self.import_module()

        with self.assertRaises(ValueError):
            mod.validate_signal_symbols({"NVDA"}, {"TSLA": {}})

    def test_build_live_payload_normalizes_single_ticker_multiindex_history(self) -> None:
        import pandas as pd

        mod = self.import_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            model_file = tmp / "model.py"
            model_file.write_text(
                """
import pandas as pd

class KronosTokenizer:
    @classmethod
    def from_pretrained(cls, name):
        return cls()

class Kronos:
    @classmethod
    def from_pretrained(cls, name):
        return cls()

class KronosPredictor:
    def __init__(self, model, tokenizer, max_context):
        self.max_context = max_context

    def predict(self, df, x_timestamp, y_timestamp, pred_len, T, top_p, sample_count):
        return pd.DataFrame({"close": [110.0 + index for index in range(pred_len)]})
""".strip(),
                encoding="utf-8",
            )

            history = pd.DataFrame(
                [
                    [100.0, 101.0, 99.0, 100.0, 1000],
                    [101.0, 102.0, 100.0, 102.0, 1100],
                    [102.0, 103.0, 101.0, 104.0, 1200],
                ],
                index=pd.date_range("2026-06-10", periods=3, freq="D", name="Date"),
                columns=pd.MultiIndex.from_product([["Open", "High", "Low", "Close", "Volume"], ["NVDA"]]),
            )

            env = {
                "KRONOS_PROJECT_ROOT": str(tmp),
                "KRONOS_TIMEFRAME": "1d",
                "KRONOS_HORIZON_BARS": "2",
                "KRONOS_LOOKBACK_BARS": "10",
            }
            with mock.patch.dict(os.environ, env, clear=False), mock.patch.dict(
                sys.modules,
                {"yfinance": types.SimpleNamespace(download=lambda *args, **kwargs: history)},
                clear=False,
            ):
                payload = mod.build_live_payload(["NVDA"], "2026-06-13", "test-universe")

            self.assertEqual(payload["data_status"], "ok")
            self.assertEqual(payload["model"]["mode"], "inference_only")
            self.assertEqual(sorted(payload["symbols"].keys()), ["NVDA"])
            self.assertEqual(payload["symbols"]["NVDA"]["direction_bias"], "bullish")
            self.assertEqual(payload["symbols"]["NVDA"]["setup_bias"], "breakout")

    def test_main_writes_failed_payload_for_live_setup_errors(self) -> None:
        mod = self.import_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            universe = tmp / "universe.txt"
            output = tmp / "kronos_signals.json"
            universe.write_text("NVDA\n", encoding="utf-8")

            args = types.SimpleNamespace(
                universe_file=str(universe),
                output_file=str(output),
                date="2026-06-13",
                mock=False,
            )
            stderr = io.StringIO()
            with (
                mock.patch.object(mod, "parse_args", return_value=args),
                mock.patch.object(mod, "build_live_payload", side_effect=RuntimeError("boom")),
                contextlib.redirect_stderr(stderr),
            ):
                exit_code = mod.main()

            self.assertEqual(exit_code, 1)
            self.assertIn("kronos signal generation failed: boom", stderr.getvalue())
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["data_status"], "failed")
            self.assertEqual(payload["symbols"], {})
            self.assertIn("boom", payload["notes"])


class KronosRunnerTests(unittest.TestCase):
    def test_mock_runner_writes_repo_state_file(self) -> None:
        state_file = REPO_ROOT / "state" / "kronos_signals.json"
        original_contents = state_file.read_text(encoding="utf-8") if state_file.exists() else None
        try:
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
        finally:
            if original_contents is None:
                state_file.unlink(missing_ok=True)
            else:
                state_file.write_text(original_contents, encoding="utf-8")
