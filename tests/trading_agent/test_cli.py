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
        self.assertIn("dashboard", result.stdout)

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
        self.assertIn("ENABLE_OHLCV_CACHE", result.stdout)
        self.assertIn("PAPER_PARTIAL_FILL", result.stdout)

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


def test_growth_observe_writes_artifact(tmp_path, monkeypatch, capsys):
    import json
    from trading_agent.cli import main

    run_dir = tmp_path / "runtime" / "state" / "runs" / "2026-06-15"
    run_dir.mkdir(parents=True)
    (run_dir / "run_manifest.json").write_text(json.dumps({"strategy_id": "baseline_v1"}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    rc = main(["growth", "observe"])
    assert rc == 0
    out = tmp_path / "runtime" / "analytics" / "growth_observations.json"
    assert out.exists()
    assert "growth_observations.json" in capsys.readouterr().out


def test_growth_propose_writes_validated_proposals(tmp_path, monkeypatch, capsys):
    import json
    from pathlib import Path
    from trading_agent.cli import main

    # Seed the real safety policy + a run that triggers a high-no-trade observation.
    config_dir = tmp_path / "src" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "growth_policy.json").write_text(
        (Path.cwd() / "src" / "config" / "growth_policy.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / "runtime" / "state" / "runs" / "2026-06-15").mkdir(parents=True)
    dec_dir = tmp_path / "runtime" / "logs" / "runs" / "2026-06-15" / "audit"
    dec_dir.mkdir(parents=True)
    with (dec_dir / "decisions.jsonl").open("w", encoding="utf-8") as fh:
        for i in range(5):
            fh.write(json.dumps({"timestamp": f"2026-06-15T07:0{i}:00-0700",
                                 "decision": "no_trade", "blocked_reasons": ["below_trade_threshold"]}) + "\n")
    monkeypatch.chdir(tmp_path)

    rc = main(["growth", "propose"])
    assert rc == 0
    assert "proposal" in capsys.readouterr().out.lower()
    proposals = list((tmp_path / "runtime" / "strategy_proposals").rglob("*.json"))
    assert proposals
    payload = json.loads(proposals[0].read_text(encoding="utf-8"))
    assert payload["validation"]["ok"] is True
    assert payload["status"] == "proposed"


def test_growth_experiments_add_approve_archive_flow(tmp_path, monkeypatch, capsys):
    import json
    from trading_agent.cli import main
    from trading_agent.growth.experiment_queue import load_experiments

    config_dir = tmp_path / "src" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "strategy_registry.yaml").write_text(
        "active_strategy: baseline_v1\nstrategies:\n  baseline_v1:\n    status: active\n", encoding="utf-8"
    )
    registry_before = (config_dir / "strategy_registry.yaml").read_text(encoding="utf-8")
    proposal_path = tmp_path / "proposal.json"
    proposal_path.write_text(json.dumps({
        "proposal_id": "2026-06-16_scoring_trade_threshold",
        "mutation": {"module": "scoring", "field": "trade_threshold", "current": 50.0, "proposed": 40.0},
    }), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["growth", "experiments", "add", str(proposal_path)]) == 0
    rows = load_experiments(tmp_path)
    assert len(rows) == 1
    exp_id = next(iter(rows))

    assert main(["growth", "experiments", "approve", exp_id]) == 0
    assert load_experiments(tmp_path)[exp_id]["status"] == "active_shadow"
    # approve must never touch the champion registry.
    assert (config_dir / "strategy_registry.yaml").read_text(encoding="utf-8") == registry_before

    assert main(["growth", "experiments", "list"]) == 0
    assert "active_shadow" in capsys.readouterr().out

    assert main(["growth", "experiments", "archive", exp_id]) == 0
    assert load_experiments(tmp_path)[exp_id]["status"] == "archived"


def test_growth_evaluate_writes_report(tmp_path, monkeypatch, capsys):
    from pathlib import Path
    from trading_agent.cli import main

    config_dir = tmp_path / "src" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "growth_policy.json").write_text(
        (Path.cwd() / "src" / "config" / "growth_policy.json").read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["growth", "evaluate"]) == 0
    assert (tmp_path / "runtime" / "analytics" / "experiment_report.json").exists()
    assert (tmp_path / "runtime" / "analytics" / "promotion_recommendation.md").exists()
    assert "experiment_report.json" in capsys.readouterr().out
