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
    def test_readme_mentions_portable_kronos_rebuild_and_validation_commands(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("./scripts/setup_kronos_env.sh", readme)
        self.assertIn("./scripts/verify_kronos_env.sh", readme)
        self.assertIn("./scripts/check_safety.sh", readme)
        self.assertIn("KRONOS_BOOTSTRAP_PYTHON", readme)
        self.assertRegex(readme, r"python3\.12|python3\.11")

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

    def test_setup_doc_mentions_bootstrap_python_override(self) -> None:
        contents = (REPO_ROOT / "docs" / "setup" / "kronos-portable-setup.md").read_text(encoding="utf-8")

        self.assertIn("KRONOS_BOOTSTRAP_PYTHON", contents)
        self.assertRegex(contents, r"python3\.12|python3\.11")

    def test_setup_script_fails_fast_when_only_unsupported_python_is_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            repo = tmp / "repo"
            fake_bin = tmp / "bin"
            (repo / "scripts").mkdir(parents=True)
            fake_bin.mkdir()

            (repo / "scripts" / "setup_kronos_env.sh").write_text(
                (REPO_ROOT / "scripts" / "setup_kronos_env.sh").read_text(encoding="utf-8"),
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
                ["/bin/bash", str(repo / "scripts" / "setup_kronos_env.sh")],
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

            (repo / "scripts").mkdir(parents=True)
            (repo / "config").mkdir()
            fake_bin.mkdir()

            (repo / "scripts" / "setup_kronos_env.sh").write_text(
                (REPO_ROOT / "scripts" / "setup_kronos_env.sh").read_text(encoding="utf-8"),
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
                ["/bin/bash", str(repo / "scripts" / "setup_kronos_env.sh")],
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
        prompt = (REPO_ROOT / "prompts" / "premarket_research.txt").read_text(encoding="utf-8")
        self.assertIn("state/kronos_signals.json", prompt)
        self.assertIn("kronos_signal_status", prompt)
        self.assertIn("kronos_direction_bias", prompt)
        self.assertIn("kronos_confidence", prompt)
        self.assertIn("kronos_setup_bias", prompt)


class SafetyWiringTests(unittest.TestCase):
    def test_check_safety_verifies_run_premarket_kronos_gate(self) -> None:
        contents = (REPO_ROOT / "scripts" / "check_safety.sh").read_text(encoding="utf-8")

        self.assertIn('ENABLE_KRONOS_SIGNAL_LAYER', contents)
        self.assertIn('scripts/run_premarket.sh', contents)
        self.assertIn('run_kronos_premarket_scan.sh', contents)

    def test_check_safety_verifies_portable_kronos_artifacts(self) -> None:
        contents = (REPO_ROOT / "scripts" / "check_safety.sh").read_text(encoding="utf-8")

        self.assertIn('config/runtime.env.local.example', contents)
        self.assertIn('requirements-kronos-extra.txt', contents)
        self.assertIn('scripts/setup_kronos_env.sh', contents)
        self.assertIn('scripts/verify_kronos_env.sh', contents)


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
    def test_premarket_runner_invokes_kronos_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            scripts_dir = tmp / "scripts"
            prompts_dir = tmp / "prompts"
            scripts_dir.mkdir()
            prompts_dir.mkdir()

            (scripts_dir / "run_premarket.sh").write_text(
                (REPO_ROOT / "scripts" / "run_premarket.sh").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (scripts_dir / "common.sh").write_text(
                """
#!/usr/bin/env bash
set -euo pipefail
AGENT_ROOT="$(pwd)"
acquire_lock() { :; }
is_weekday_pt() { return 0; }
log_line() { printf 'log:%s\\n' "$*" >> "$AGENT_ROOT/calls.log"; }
run_codex_prompt() { printf 'prompt:%s:%s\\n' "$1" "$2" >> "$AGENT_ROOT/calls.log"; }
""".strip()
                + "\n",
                encoding="utf-8",
            )
            (scripts_dir / "run_kronos_premarket_scan.sh").write_text(
                """
#!/usr/bin/env bash
set -euo pipefail
printf 'kronos\\n' >> "$(pwd)/calls.log"
""".strip()
                + "\n",
                encoding="utf-8",
            )
            (prompts_dir / "premarket_research.txt").write_text("prompt\n", encoding="utf-8")
            os.chmod(scripts_dir / "run_kronos_premarket_scan.sh", 0o755)

            env = dict(os.environ, ENABLE_DSA_SIGNAL_LAYER="0", ENABLE_KRONOS_SIGNAL_LAYER="1")
            result = subprocess.run(
                ["bash", str(scripts_dir / "run_premarket.sh")],
                capture_output=True,
                text=True,
                check=False,
                cwd=tmp,
                env=env,
            )

            self.assertEqual(result.returncode, 0)
            calls = (tmp / "calls.log").read_text(encoding="utf-8").splitlines()
            self.assertEqual(calls[0], "kronos")
            self.assertEqual(len(calls), 2)
            self.assertTrue(calls[1].startswith("prompt:premarket:"))
            self.assertTrue(calls[1].endswith("/prompts/premarket_research.txt"))

    def test_premarket_runner_skips_kronos_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            scripts_dir = tmp / "scripts"
            prompts_dir = tmp / "prompts"
            scripts_dir.mkdir()
            prompts_dir.mkdir()

            (scripts_dir / "run_premarket.sh").write_text(
                (REPO_ROOT / "scripts" / "run_premarket.sh").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (scripts_dir / "common.sh").write_text(
                """
#!/usr/bin/env bash
set -euo pipefail
AGENT_ROOT="$(pwd)"
acquire_lock() { :; }
is_weekday_pt() { return 0; }
log_line() { printf 'log:%s\\n' "$*" >> "$AGENT_ROOT/calls.log"; }
run_codex_prompt() { printf 'prompt:%s:%s\\n' "$1" "$2" >> "$AGENT_ROOT/calls.log"; }
""".strip()
                + "\n",
                encoding="utf-8",
            )
            (scripts_dir / "run_kronos_premarket_scan.sh").write_text(
                """
#!/usr/bin/env bash
set -euo pipefail
printf 'kronos\\n' >> "$(pwd)/calls.log"
""".strip()
                + "\n",
                encoding="utf-8",
            )
            (prompts_dir / "premarket_research.txt").write_text("prompt\n", encoding="utf-8")
            os.chmod(scripts_dir / "run_kronos_premarket_scan.sh", 0o755)

            env = dict(os.environ, ENABLE_DSA_SIGNAL_LAYER="0", ENABLE_KRONOS_SIGNAL_LAYER="0")
            result = subprocess.run(
                ["bash", str(scripts_dir / "run_premarket.sh")],
                capture_output=True,
                text=True,
                check=False,
                cwd=tmp,
                env=env,
            )

            self.assertEqual(result.returncode, 0)
            calls = (tmp / "calls.log").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(calls), 1)
            self.assertTrue(calls[0].startswith("prompt:premarket:"))
            self.assertTrue(calls[0].endswith("/prompts/premarket_research.txt"))

    def test_premarket_runner_continues_when_kronos_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            scripts_dir = tmp / "scripts"
            prompts_dir = tmp / "prompts"
            scripts_dir.mkdir()
            prompts_dir.mkdir()

            (scripts_dir / "run_premarket.sh").write_text(
                (REPO_ROOT / "scripts" / "run_premarket.sh").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (scripts_dir / "common.sh").write_text(
                """
#!/usr/bin/env bash
set -euo pipefail
AGENT_ROOT="$(pwd)"
acquire_lock() { :; }
is_weekday_pt() { return 0; }
log_line() { printf 'log:%s\\n' "$*" >> "$AGENT_ROOT/calls.log"; }
run_codex_prompt() { printf 'prompt:%s:%s\\n' "$1" "$2" >> "$AGENT_ROOT/calls.log"; }
""".strip()
                + "\n",
                encoding="utf-8",
            )
            (scripts_dir / "run_kronos_premarket_scan.sh").write_text(
                """
#!/usr/bin/env bash
set -euo pipefail
printf 'kronos\\n' >> "$(pwd)/calls.log"
exit 7
""".strip()
                + "\n",
                encoding="utf-8",
            )
            (prompts_dir / "premarket_research.txt").write_text("prompt\n", encoding="utf-8")
            os.chmod(scripts_dir / "run_kronos_premarket_scan.sh", 0o755)

            env = dict(os.environ, ENABLE_DSA_SIGNAL_LAYER="0", ENABLE_KRONOS_SIGNAL_LAYER="1")
            result = subprocess.run(
                ["bash", str(scripts_dir / "run_premarket.sh")],
                capture_output=True,
                text=True,
                check=False,
                cwd=tmp,
                env=env,
            )

            self.assertEqual(result.returncode, 0)
            calls = (tmp / "calls.log").read_text(encoding="utf-8").splitlines()
            self.assertEqual(calls[0], "kronos")
            self.assertEqual(
                calls[1],
                "log:kronos_premarket_scan failed; continuing with main premarket research.",
            )
            self.assertEqual(len(calls), 3)
            self.assertTrue(calls[2].startswith("prompt:premarket:"))
            self.assertTrue(calls[2].endswith("/prompts/premarket_research.txt"))

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
