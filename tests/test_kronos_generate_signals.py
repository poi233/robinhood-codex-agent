import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


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
