import contextlib
import io
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from trading_agent.core.time import pt_date_string
from trading_agent.signals.kronos import build_mock_kronos_payload

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "kronos" / "kronos_generate_signals.py"
RUNNER_PATH = REPO_ROOT / "scripts" / "kronos" / "run_kronos_premarket_scan.sh"


def kronos_run_output(root: Path, run_date: str | None = None) -> Path:
    resolved_date = run_date or pt_date_string()
    return root / "state" / "runs" / resolved_date / "signals" / "kronos_signals.json"


class CommonRuntimeTests(unittest.TestCase):
    def test_common_sh_prefers_runtime_env_local(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            config_dir = tmp / "config"
            scripts_dir = tmp / "scripts"
            config_dir.mkdir()
            (scripts_dir / "lib").mkdir(parents=True)

            (config_dir / "runtime.env").write_text("TRADING_MODE=paper\n", encoding="utf-8")
            (config_dir / "runtime.env.local").write_text("TRADING_MODE=review\n", encoding="utf-8")
            (scripts_dir / "lib" / "common.sh").write_text((REPO_ROOT / "scripts" / "lib" / "common.sh").read_text(encoding="utf-8"), encoding="utf-8")

            result = subprocess.run(
                ["bash", "-lc", f"cd {tmp} && source scripts/lib/common.sh && printf '%s' \"$TRADING_MODE\""],
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
            (scripts_dir / "lib").mkdir(parents=True)

            (config_dir / "runtime.env").write_text("TRADING_MODE=paper\n", encoding="utf-8")
            (scripts_dir / "lib" / "common.sh").write_text((REPO_ROOT / "scripts" / "lib" / "common.sh").read_text(encoding="utf-8"), encoding="utf-8")

            result = subprocess.run(
                [
                    "bash",
                    "-lc",
                    (
                        f"cd {tmp} && source scripts/lib/common.sh && "
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
            (scripts_dir / "lib").mkdir(parents=True)

            (config_dir / "runtime.env").write_text("TRADING_MODE=paper\n", encoding="utf-8")
            (config_dir / "runtime.env.local").write_text("TRADING_MODE=review\n", encoding="utf-8")
            (scripts_dir / "lib" / "common.sh").write_text((REPO_ROOT / "scripts" / "lib" / "common.sh").read_text(encoding="utf-8"), encoding="utf-8")

            env = dict(**os.environ, TRADING_MODE="live")
            result = subprocess.run(
                ["bash", "-lc", f"cd {tmp} && source scripts/lib/common.sh && printf '%s' \"$TRADING_MODE\""],
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )

            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "live")


class PortableArtifactTests(unittest.TestCase):
    def test_readme_mentions_portable_kronos_rebuild_and_validation_commands(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("./scripts/kronos/setup_kronos_env.sh", readme)
        self.assertIn("./scripts/kronos/verify_kronos_env.sh", readme)
        self.assertIn("./scripts/safety/check_safety.sh", readme)
        self.assertIn("ALLOW_WEEKEND_RUN=1 KRONOS_USE_MOCK=1 ./scripts/kronos/run_kronos_premarket_scan.sh", readme)
        self.assertIn(
            "ALLOW_WEEKEND_RUN=1 CODEX_EXEC_DRY_RUN=1 ./scripts/entrypoints/run_premarket.sh",
            readme,
        )
        self.assertIn("KRONOS_BOOTSTRAP_PYTHON", readme)
        self.assertRegex(readme, r"python3\.12|python3\.11")

    def test_runtime_env_local_example_exists(self) -> None:
        self.assertTrue((REPO_ROOT / "config" / "runtime.env.local.example").exists())

    def test_requirements_kronos_extra_exists(self) -> None:
        self.assertTrue((REPO_ROOT / "requirements-kronos-extra.txt").exists())

    def test_setup_and_verify_scripts_exist(self) -> None:
        self.assertTrue((REPO_ROOT / "scripts" / "kronos" / "setup_kronos_env.sh").exists())
        self.assertTrue((REPO_ROOT / "scripts" / "kronos" / "verify_kronos_env.sh").exists())

    def test_verify_script_runs_signal_generation_verification(self) -> None:
        contents = (REPO_ROOT / "scripts" / "kronos" / "verify_kronos_env.sh").read_text(encoding="utf-8")

        self.assertIn('"$AGENT_ROOT/scripts/kronos/kronos_generate_signals.py"', contents)
        self.assertNotIn("pending Task 3", contents)

    def test_verify_script_uses_temp_output_and_cleans_it_up(self) -> None:
        contents = (REPO_ROOT / "scripts" / "kronos" / "verify_kronos_env.sh").read_text(encoding="utf-8")

        self.assertIn("mktemp", contents)
        self.assertIn("trap", contents)
        self.assertNotIn('state/kronos_signals.json', contents)
        self.assertNotIn('mktemp "$AGENT_ROOT/state/kronos_signals.verify.XXXXXX.json"', contents)

    def test_readme_carries_portable_setup_flow(self) -> None:
        contents = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("Portable rebuild and validation flow", contents)
        self.assertIn("./scripts/kronos/verify_kronos_env.sh", contents)
        self.assertIn("./scripts/safety/check_safety.sh", contents)
        self.assertIn("ALLOW_WEEKEND_RUN=1 KRONOS_USE_MOCK=1 ./scripts/kronos/run_kronos_premarket_scan.sh", contents)
        self.assertIn(
            "ALLOW_WEEKEND_RUN=1 CODEX_EXEC_DRY_RUN=1 ./scripts/entrypoints/run_premarket.sh",
            contents,
        )
        self.assertIn("KRONOS_BOOTSTRAP_PYTHON", contents)
        self.assertRegex(contents, r"python3\.12|python3\.11")

    def test_docs_directory_is_not_tracked_requirement_in_tests(self) -> None:
        self.assertTrue((REPO_ROOT / "README.md").exists())

    def test_setup_script_fails_fast_when_only_unsupported_python_is_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            repo = tmp / "repo"
            fake_bin = tmp / "bin"
            (repo / "scripts" / "kronos").mkdir(parents=True)
            fake_bin.mkdir()

            (repo / "scripts" / "kronos" / "setup_kronos_env.sh").write_text(
                (REPO_ROOT / "scripts" / "kronos" / "setup_kronos_env.sh").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (fake_bin / "git").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            (fake_bin / "python3").write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = \"-c\" ]; then\n"
                "  printf '3.13\\n'\n"
                "  exit 0\n"
                "fi\n"
                "exit 0\n",
                encoding="utf-8",
            )
            os.chmod(fake_bin / "git", 0o755)
            os.chmod(fake_bin / "python3", 0o755)

            result = subprocess.run(
                ["/bin/bash", str(repo / "scripts" / "kronos" / "setup_kronos_env.sh")],
                cwd=repo,
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}"},
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("KRONOS_BOOTSTRAP_PYTHON", result.stderr)
            self.assertIn("python3.12", result.stderr)
            self.assertIn("python3.11", result.stderr)
            self.assertIn("3.13", result.stderr)

    def test_setup_script_prefers_compatible_python_when_python3_is_unsupported(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            repo = tmp / "repo"
            fake_bin = tmp / "bin"
            venv_python_log = tmp / "venv-python.log"
            pip_log = tmp / "pip.log"
            git_log = tmp / "git.log"

            (repo / "scripts" / "kronos").mkdir(parents=True)
            (repo / "config").mkdir()
            fake_bin.mkdir()

            (repo / "scripts" / "kronos" / "setup_kronos_env.sh").write_text(
                (REPO_ROOT / "scripts" / "kronos" / "setup_kronos_env.sh").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (repo / "config" / "runtime.env.local.example").write_text("TRADING_MODE=paper\n", encoding="utf-8")
            (repo / "requirements-kronos-extra.txt").write_text("example-extra\n", encoding="utf-8")

            (fake_bin / "git").write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' \"$*\" >> \"$GIT_LOG\"\n"
                "if [ \"$1\" = \"clone\" ]; then\n"
                "  target=\"$3\"\n"
                "  mkdir -p \"$target/.git\"\n"
                "  printf 'example-package\\n' > \"$target/requirements.txt\"\n"
                "fi\n"
                "exit 0\n",
                encoding="utf-8",
            )
            (fake_bin / "python3").write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = \"-c\" ]; then\n"
                "  printf '3.13\\n'\n"
                "  exit 0\n"
                "fi\n"
                "exit 0\n",
                encoding="utf-8",
            )
            (fake_bin / "python3.11").write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = \"-c\" ]; then\n"
                "  printf '3.11\\n'\n"
                "  exit 0\n"
                "fi\n"
                "if [ \"$1\" = \"-m\" ] && [ \"$2\" = \"venv\" ]; then\n"
                "  venv_dir=\"$3\"\n"
                "  mkdir -p \"$venv_dir/bin\"\n"
                "  cat > \"$venv_dir/bin/python\" <<'EOF'\n"
                "#!/bin/sh\n"
                "printf '%s\\n' \"$0 $*\" >> \"$VENV_PYTHON_LOG\"\n"
                "if [ \"$1\" = \"-m\" ] && [ \"$2\" = \"pip\" ]; then\n"
                "  exit 0\n"
                "fi\n"
                "exit 0\n"
                "EOF\n"
                "  cat > \"$venv_dir/bin/pip\" <<'EOF'\n"
                "#!/bin/sh\n"
                "printf '%s\\n' \"$0 $*\" >> \"$PIP_LOG\"\n"
                "exit 0\n"
                "EOF\n"
                "  chmod +x \"$venv_dir/bin/python\" \"$venv_dir/bin/pip\"\n"
                "  exit 0\n"
                "fi\n"
                "exit 0\n",
                encoding="utf-8",
            )
            for path in (fake_bin / "git", fake_bin / "python3", fake_bin / "python3.11"):
                os.chmod(path, 0o755)

            result = subprocess.run(
                ["/bin/bash", str(repo / "scripts" / "kronos" / "setup_kronos_env.sh")],
                cwd=repo,
                capture_output=True,
                text=True,
                check=False,
                env={
                    **os.environ,
                    "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
                    "GIT_LOG": str(git_log),
                    "VENV_PYTHON_LOG": str(venv_python_log),
                    "PIP_LOG": str(pip_log),
                },
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertTrue((repo / "config" / "runtime.env.local").exists())
            env_contents = (repo / "config" / "runtime.env.local").read_text(encoding="utf-8")
            self.assertIn(f"KRONOS_PYTHON_BIN={repo / '.venv-kronos' / 'bin' / 'python'}", env_contents)
            self.assertIn(f"KRONOS_PROJECT_ROOT={repo / '.vendor' / 'kronos'}", env_contents)
            self.assertIn("python3.11", result.stdout)
            self.assertTrue(venv_python_log.exists())
            self.assertTrue(pip_log.exists())



class PromptWiringTests(unittest.TestCase):
    def test_premarket_prompt_mentions_kronos_signal_file(self) -> None:
        prompt = (REPO_ROOT / "prompts" / "premarket" / "final_research.txt").read_text(encoding="utf-8")
        self.assertIn("KRONOS_SIGNALS_PATH", prompt)
        self.assertIn("kronos_signal_status", prompt)
        self.assertIn("kronos_direction_bias", prompt)
        self.assertIn("kronos_confidence", prompt)
        self.assertIn("kronos_setup_bias", prompt)


class SafetyWiringTests(unittest.TestCase):
    def test_check_safety_verifies_run_premarket_kronos_gate(self) -> None:
        contents = (REPO_ROOT / "scripts" / "safety" / "check_safety.sh").read_text(encoding="utf-8")

        self.assertIn('ENABLE_KRONOS_SIGNAL_LAYER', contents)
        self.assertIn('scripts/entrypoints/run_premarket.sh', contents)
        self.assertIn('trading_agent/orchestration/premarket.py', contents)

    def test_check_safety_verifies_portable_kronos_artifacts(self) -> None:
        contents = (REPO_ROOT / "scripts" / "safety" / "check_safety.sh").read_text(encoding="utf-8")

        self.assertIn('config/runtime.env.local.example', contents)
        self.assertIn('requirements-kronos-extra.txt', contents)
        self.assertIn('scripts/kronos/setup_kronos_env.sh', contents)
        self.assertIn('scripts/kronos/verify_kronos_env.sh', contents)

    def test_check_safety_runs_without_rg_binary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            scripts_dir = tmp / "scripts"
            config_dir = tmp / "config"
            prompts_dir = tmp / "prompts"
            codex_dir = tmp / ".codex"
            fake_bin = tmp / "bin"

            scripts_dir.mkdir()
            (scripts_dir / "lib").mkdir()
            (scripts_dir / "safety").mkdir()
            (scripts_dir / "kronos").mkdir()
            (scripts_dir / "entrypoints").mkdir()
            config_dir.mkdir()
            prompts_dir.mkdir()
            (prompts_dir / "premarket").mkdir()
            (prompts_dir / "postmarket").mkdir()
            (prompts_dir / "signals").mkdir()
            (prompts_dir / "technical").mkdir()
            (prompts_dir / "intraday").mkdir()
            codex_dir.mkdir()
            fake_bin.mkdir()

            (scripts_dir / "safety" / "check_safety.sh").write_text(
                (REPO_ROOT / "scripts" / "safety" / "check_safety.sh").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (scripts_dir / "lib" / "common.sh").write_text(
                (REPO_ROOT / "scripts" / "lib" / "common.sh").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            (config_dir / "runtime.env").write_text(
                "TRADING_MODE=paper\nRISK_TIER=0\nENABLE_KRONOS_SIGNAL_LAYER=1\n",
                encoding="utf-8",
            )
            (config_dir / "allowlist.txt").write_text("SPY\n", encoding="utf-8")
            (config_dir / "universe.txt").write_text("NVDA\n", encoding="utf-8")
            (config_dir / "risk.md").write_text("Only use limit orders\n", encoding="utf-8")
            (config_dir / "dsa_strategy_weights.json").write_text("{}\n", encoding="utf-8")
            (config_dir / "runtime.env.local.example").write_text("TRADING_MODE=paper\n", encoding="utf-8")

            (prompts_dir / "premarket/final_research.txt").write_text(
                "Do not call place_equity_order\nDSA_SIGNALS_PATH\nKRONOS_SIGNALS_PATH\nTECHNICAL_SIGNALS_PATH\n",
                encoding="utf-8",
            )
            (prompts_dir / "postmarket/summary.txt").write_text(
                "Do not call place_equity_order\n",
                encoding="utf-8",
            )
            (prompts_dir / "signals/dsa_scan.txt").write_text(
                "never place, review, cancel, or modify orders\n",
                encoding="utf-8",
            )
            (prompts_dir / "technical/research.txt").write_text("TECHNICAL_SIGNALS_PATH\n", encoding="utf-8")
            (prompts_dir / "intraday/check.txt").write_text(
                "Runtime mode behavior\nDSA_SIGNALS_PATH\nTECHNICAL_SIGNALS_PATH\n",
                encoding="utf-8",
            )

            for filename in ("setup_kronos_env.sh", "verify_kronos_env.sh"):
                (scripts_dir / "kronos" / filename).write_text("", encoding="utf-8")
            (scripts_dir / "kronos" / "kronos_generate_signals.py").write_text("", encoding="utf-8")
            (scripts_dir / "entrypoints" / "run_premarket.sh").write_text(
                'python3 -m trading_agent premarket\n',
                encoding="utf-8",
            )
            (tmp / "trading_agent" / "orchestration").mkdir(parents=True)
            (tmp / "trading_agent" / "__init__.py").write_text("", encoding="utf-8")
            (tmp / "trading_agent" / "orchestration" / "__init__.py").write_text("", encoding="utf-8")
            (tmp / "trading_agent" / "orchestration" / "premarket.py").write_text(
                'ENABLE_KRONOS_SIGNAL_LAYER = "1"\n'
                "def _write_kronos_signals():\n"
                "    pass\n"
                "def collect_market_context():\n"
                "    pass\n"
                'TECHNICAL_PROMPT = "technical/research.txt"\n',
                encoding="utf-8",
            )

            (tmp / "requirements-kronos-extra.txt").write_text("yfinance\n", encoding="utf-8")
            (codex_dir / "config.toml").write_text("", encoding="utf-8")
            (fake_bin / "rg").write_text("#!/bin/sh\nexit 86\n", encoding="utf-8")
            os.chmod(fake_bin / "rg", 0o755)

            result = subprocess.run(
                ["/bin/bash", str(scripts_dir / "safety" / "check_safety.sh")],
                cwd=tmp,
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}"},
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("Safety checks:", result.stdout)
            self.assertIn("Kronos signal layer is configured and wired into premarket: ok", result.stdout)
            self.assertIn("Technical signal layer is configured and wired into premarket/intraday: ok", result.stdout)


class KronosGenerateSignalsTests(unittest.TestCase):
    @staticmethod
    def import_module():
        scripts_path = str(REPO_ROOT / "scripts" / "kronos")
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
        if not hasattr(x_timestamp, "dt") or not hasattr(y_timestamp, "dt"):
            raise TypeError("timestamps must be pandas Series with .dt accessors")
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


class KronosPackageApiTests(unittest.TestCase):
    def test_build_mock_kronos_payload_returns_expected_symbols(self) -> None:
        payload = build_mock_kronos_payload(["NVDA", "PLTR"], "2026-06-14", "config/universe.txt")
        self.assertEqual(payload["date"], "2026-06-14")
        self.assertEqual(sorted(payload["symbols"].keys()), ["NVDA", "PLTR"])


class KronosRunnerTests(unittest.TestCase):
    def build_temp_runtime_repo(self, tmp: Path) -> None:
        shutil.copytree(REPO_ROOT / "trading_agent", tmp / "trading_agent")
        (tmp / "scripts" / "entrypoints").mkdir(parents=True)
        (tmp / "scripts" / "lib").mkdir()
        (tmp / "scripts" / "kronos").mkdir()
        (tmp / "config").mkdir()
        (tmp / "prompts" / "premarket").mkdir(parents=True)
        (tmp / "prompts" / "signals").mkdir()
        (tmp / "prompts" / "technical").mkdir()
        (tmp / "state").mkdir()
        (tmp / "logs").mkdir()

        (tmp / "scripts" / "entrypoints" / "run_premarket.sh").write_text(
            (REPO_ROOT / "scripts" / "entrypoints" / "run_premarket.sh").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (tmp / "scripts" / "lib" / "common.sh").write_text(
            (REPO_ROOT / "scripts" / "lib" / "common.sh").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (tmp / "scripts" / "kronos" / "kronos_generate_signals.py").write_text(
            SCRIPT_PATH.read_text(encoding="utf-8"),
            encoding="utf-8",
        )

        (tmp / "config" / "runtime.env").write_text(
            "\n".join(
                [
                    "TRADING_MODE=paper",
                    "CODEX_MODEL=gpt-5.5",
                    "ENABLE_DSA_SIGNAL_LAYER=0",
                    "ENABLE_KRONOS_SIGNAL_LAYER=1",
                    "ENABLE_MARKET_FEED_LAYER=0",
                    "ENABLE_TECHNICAL_SIGNAL_LAYER=0",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (tmp / "config" / "universe.txt").write_text("NVDA\nPLTR\n", encoding="utf-8")
        for prompt_name in (
            "account_snapshot.txt",
            "market_calendar.txt",
            "quote_snapshot_core.txt",
            "quote_snapshot_candidates.txt",
            "tradability_candidates.txt",
            "catalyst_enrichment.txt",
            "final_research.txt",
        ):
            (tmp / "prompts" / "premarket" / prompt_name).write_text("prompt\n", encoding="utf-8")
        (tmp / "prompts" / "signals" / "dsa_scan.txt").write_text("prompt\n", encoding="utf-8")
        (tmp / "prompts" / "technical" / "research.txt").write_text("prompt\n", encoding="utf-8")

    def test_premarket_runner_invokes_kronos_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            self.build_temp_runtime_repo(tmp)

            env = dict(
                os.environ,
                ALLOW_WEEKEND_RUN="1",
                CODEX_EXEC_DRY_RUN="1",
                KRONOS_USE_MOCK="1",
            )
            result = subprocess.run(
                ["bash", str(tmp / "scripts" / "entrypoints" / "run_premarket.sh")],
                capture_output=True,
                text=True,
                check=False,
                cwd=tmp,
                env=env,
            )

            self.assertEqual(result.returncode, 0)
            payload = json.loads(kronos_run_output(tmp).read_text(encoding="utf-8"))
            self.assertEqual(payload["data_status"], "ok")
            self.assertIn("NVDA", payload["symbols"])

    def test_premarket_runner_skips_kronos_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            self.build_temp_runtime_repo(tmp)
            (tmp / "config" / "runtime.env").write_text(
                "\n".join(
                    [
                        "TRADING_MODE=paper",
                        "ENABLE_DSA_SIGNAL_LAYER=0",
                        "ENABLE_KRONOS_SIGNAL_LAYER=0",
                        "ENABLE_MARKET_FEED_LAYER=0",
                        "ENABLE_TECHNICAL_SIGNAL_LAYER=0",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            env = dict(
                os.environ,
                ALLOW_WEEKEND_RUN="1",
                CODEX_EXEC_DRY_RUN="1",
            )
            result = subprocess.run(
                ["bash", str(tmp / "scripts" / "entrypoints" / "run_premarket.sh")],
                capture_output=True,
                text=True,
                check=False,
                cwd=tmp,
                env=env,
            )

            self.assertEqual(result.returncode, 0)
            self.assertFalse(kronos_run_output(tmp).exists())

    def test_premarket_runner_continues_when_kronos_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            self.build_temp_runtime_repo(tmp)

            env = dict(
                os.environ,
                ALLOW_WEEKEND_RUN="1",
                CODEX_EXEC_DRY_RUN="1",
                KRONOS_PROJECT_ROOT=str(tmp / "missing-kronos-project"),
            )
            result = subprocess.run(
                ["bash", str(tmp / "scripts" / "entrypoints" / "run_premarket.sh")],
                capture_output=True,
                text=True,
                check=False,
                cwd=tmp,
                env=env,
            )

            self.assertEqual(result.returncode, 0)
            payload = json.loads(kronos_run_output(tmp).read_text(encoding="utf-8"))
            self.assertEqual(payload["data_status"], "failed")

    def test_mock_runner_writes_repo_state_file(self) -> None:
        state_file = kronos_run_output(REPO_ROOT)
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
