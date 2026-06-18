import subprocess
import sys
import unittest
from unittest import mock
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
        self.assertIn("nightly-analysis", result.stdout)
        self.assertIn("dashboard", result.stdout)

    def test_parser_accepts_runtime_subcommands(self) -> None:
        env = {**__import__("os").environ, "PYTHONPATH": str(REPO_ROOT / "src")}
        for command in ("premarket", "intraday", "postmarket", "nightly-analysis"):
            with self.subTest(command=command):
                result = subprocess.run(
                    [sys.executable, "-m", "trading_agent", command, "--help"],
                    cwd=REPO_ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                    env=env,
                )
                self.assertEqual(result.returncode, 0, msg=result.stderr)
                self.assertIn(command, result.stdout)
                if command != "nightly-analysis":
                    self.assertIn("--dry-run", result.stdout)

    def test_nightly_analysis_can_be_disabled_without_side_effects(self) -> None:
        from trading_agent.cli import main

        import os
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src" / "trading_agent").mkdir(parents=True)
            with mock.patch("trading_agent.cli.resolve_agent_root", return_value=root), \
                    mock.patch.dict(os.environ, {"ENABLE_NIGHTLY_ANALYSIS": "0"}, clear=False):
                self.assertEqual(main(["nightly-analysis"]), 0)

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

    def test_doctor_reports_launchd_scheduling(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "trading_agent", "doctor"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            env={**__import__("os").environ, "PYTHONPATH": str(REPO_ROOT / "src")},
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("Scheduling (launchd)", result.stdout)
        # The labels come from launchd/*.plist.example, so each job should be named.
        for job in ("premarket", "intraday", "postmarket", "nightly-analysis"):
            self.assertIn(f"robinhood-codex-agent.{job}", result.stdout)

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
    # main() resolves its root from the code location (cron robustness), not cwd, so point it at the
    # tmp sandbox explicitly — otherwise the command would read/write the real repo.
    monkeypatch.setattr("trading_agent.cli.resolve_agent_root", lambda: tmp_path)

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
    # main() resolves its root from the code location (cron robustness), not cwd, so point it at the
    # tmp sandbox explicitly — otherwise the command would read/write the real repo.
    monkeypatch.setattr("trading_agent.cli.resolve_agent_root", lambda: tmp_path)

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
    # main() resolves its root from the code location (cron robustness), not cwd, so point it at the
    # tmp sandbox explicitly — otherwise the command would read/write the real repo.
    monkeypatch.setattr("trading_agent.cli.resolve_agent_root", lambda: tmp_path)

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
    # main() resolves its root from the code location (cron robustness), not cwd, so point it at the
    # tmp sandbox explicitly — otherwise the command would read/write the real repo.
    monkeypatch.setattr("trading_agent.cli.resolve_agent_root", lambda: tmp_path)

    assert main(["growth", "evaluate"]) == 0
    assert (tmp_path / "runtime" / "analytics" / "experiment_report.json").exists()
    assert (tmp_path / "runtime" / "analytics" / "promotion_recommendation.md").exists()
    assert "experiment_report.json" in capsys.readouterr().out


def test_growth_promote_check_drafts_without_touching_registry(tmp_path, monkeypatch, capsys):
    import json
    from pathlib import Path
    from trading_agent.cli import main

    config_dir = tmp_path / "src" / "config"
    config_dir.mkdir(parents=True)
    registry = config_dir / "strategy_registry.yaml"
    registry.write_text("active_strategy: baseline_v1\nstrategies:\n  baseline_v1:\n    status: active\n", encoding="utf-8")
    registry_before = registry.read_text(encoding="utf-8")
    (config_dir / "growth_policy.json").write_text(json.dumps({
        "mode": "paper_only",
        "promotion_rules": {"min_shadow_days": 1, "fill_rate_not_worse_than_champion": False,
                            "max_drawdown_not_worse_than_champion": False, "require_human_final_approval": True},
    }), encoding="utf-8")
    (config_dir / "strategy_experiments.yaml").write_text(
        "experiments:\n  exp_x:\n    status: ready_for_review\n"
        "    challenger_strategy_id: \"baseline_v1__trade_threshold_40\"\n"
        "    parent_strategy_id: baseline_v1\n    module: scoring\n    field: trade_threshold\n"
        "    current: 50.0\n    proposed: 40.0\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    # main() resolves its root from the code location (cron robustness), not cwd, so point it at the
    # tmp sandbox explicitly — otherwise the command would read/write the real repo.
    monkeypatch.setattr("trading_agent.cli.resolve_agent_root", lambda: tmp_path)

    assert main(["growth", "promote", "check", "exp_x"]) == 0
    assert "exp_x" in capsys.readouterr().out
    assert (tmp_path / "runtime" / "analytics" / "promotion_drafts" / "exp_x.md").exists()
    # The command must never modify the champion registry.
    assert registry.read_text(encoding="utf-8") == registry_before


def test_analytics_calibrate_writes_report(tmp_path, monkeypatch, capsys):
    from trading_agent.cli import main
    from trading_agent.core.io import write_json
    rd = "2026-06-15"
    write_json(tmp_path / "runtime" / "state" / "runs" / rd / "planner" / "candidate_scores.json",
               {"symbols": {"NVDA": {"score": 66.0, "total_score": 66.0, "score_status": "scored", "components": {}}}})
    monkeypatch.chdir(tmp_path)
    # main() resolves its root from the code location (cron robustness), not cwd, so point it at the
    # tmp sandbox explicitly — otherwise the command would read/write the real repo.
    monkeypatch.setattr("trading_agent.cli.resolve_agent_root", lambda: tmp_path)
    # Inject an offline price loader so no network is needed.
    import trading_agent.replay.forward_returns as fr
    import trading_agent.replay.benchmark_returns as br
    monkeypatch.setattr(fr, "default_price_loader", lambda s, a, b: [(rd, 100.0), ("2026-06-16", 101.0)])
    monkeypatch.setattr(br, "default_price_loader", lambda s, a, b: [(rd, 100.0), ("2026-06-16", 101.0)])
    rc = main(["analytics", "calibrate"])
    assert rc == 0
    assert (tmp_path / "runtime" / "analytics" / "calibration_report.json").exists()
    assert "calibration_report" in capsys.readouterr().out
