import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SCRIPT = REPO_ROOT / "scripts" / "install_repo_skills.sh"
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_repo_skills.sh"


class RepoSkillInstallTests(unittest.TestCase):
    def test_install_and_verify_scripts_exist(self) -> None:
        self.assertTrue(INSTALL_SCRIPT.exists())
        self.assertTrue(VERIFY_SCRIPT.exists())

    def test_install_script_copies_repo_skills_into_both_destinations(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            agents_home = tmp / ".agents" / "skills"
            codex_home = tmp / ".codex" / "skills"
            env = {
                **os.environ,
                "HOME": str(tmp),
                "REPO_SKILL_TARGETS": f"{agents_home}:{codex_home}",
            }

            result = subprocess.run(
                ["bash", str(INSTALL_SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            for target in (agents_home, codex_home):
                self.assertTrue((target / "chan-structure-trading" / "SKILL.md").exists())
                self.assertTrue((target / "brooks-trading-range-price-action" / "references").exists())
                self.assertTrue((target / "trading-research-casebook-maintenance" / "case-update-log.md").exists())


class CommonRuntimeSkillFeedTests(unittest.TestCase):
    def test_common_sh_exports_market_feed_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "config").mkdir()
            (tmp / "scripts").mkdir()
            (tmp / "config" / "runtime.env").write_text("TRADING_MODE=paper\n", encoding="utf-8")
            (tmp / "scripts" / "common.sh").write_text(
                (REPO_ROOT / "scripts" / "common.sh").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    "bash",
                    "-lc",
                    (
                        f"cd {tmp} && source scripts/common.sh && "
                        "printf '%s\\n%s\\n%s\\n%s\\n%s' "
                        "\"$ENABLE_MARKET_FEED_LAYER\" "
                        "\"$MARKET_FEED_DIR\" "
                        "\"$RUN_STATE_DIR\" "
                        "\"$DSA_SIGNALS_PATH\" "
                        "\"$TECHNICAL_SIGNALS_PATH\""
                    ),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertIn("/state/runs/", result.stdout)
            self.assertIn("/market_feed", result.stdout)
            self.assertIn("/signals/technical_signals.json", result.stdout)

    def test_common_sh_preserves_market_feed_dir_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            override_dir = tmp / "custom-feed"
            (tmp / "config").mkdir()
            (tmp / "scripts").mkdir()
            (tmp / "config" / "runtime.env").write_text("TRADING_MODE=paper\n", encoding="utf-8")
            (tmp / "scripts" / "common.sh").write_text(
                (REPO_ROOT / "scripts" / "common.sh").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    "bash",
                    "-lc",
                    f"cd {tmp} && export MARKET_FEED_DIR={override_dir} && source scripts/common.sh && printf '%s' \"$MARKET_FEED_DIR\"",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, str(override_dir))

    def test_market_feed_python_resolver_accepts_configured_python_with_yfinance(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            fake_python = tmp / "fake-python"
            (tmp / "config").mkdir()
            (tmp / "scripts").mkdir()
            (tmp / "config" / "runtime.env").write_text("TRADING_MODE=paper\n", encoding="utf-8")
            (tmp / "scripts" / "common.sh").write_text(
                (REPO_ROOT / "scripts" / "common.sh").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            fake_python.write_text(
                "#!/usr/bin/env bash\n"
                "if [[ \"$1\" == \"-c\" && \"$2\" == \"import yfinance\" ]]; then exit 0; fi\n"
                "exit 1\n",
                encoding="utf-8",
            )
            fake_python.chmod(0o755)

            result = subprocess.run(
                [
                    "bash",
                    "-lc",
                    (
                        f"cd {tmp} && export MARKET_FEED_PYTHON_BIN={fake_python} && "
                        "source scripts/common.sh && resolve_market_feed_python_bin"
                    ),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertEqual(result.stdout.strip(), str(fake_python))
