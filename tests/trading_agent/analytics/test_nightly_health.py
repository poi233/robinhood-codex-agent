from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trading_agent.analytics.nightly_health import build_nightly_health, write_nightly_health
from trading_agent.core.io import write_json


def _fresh(hours_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


def _seed_reports(agent_root: Path, ages: dict[str, float]) -> None:
    a = agent_root / "runtime" / "analytics"
    a.mkdir(parents=True, exist_ok=True)
    for name, age in ages.items():
        write_json(a / name, {"generated_at": _fresh(age)})


def test_all_fresh_reports_ok(tmp_path):
    _seed_reports(tmp_path, {n: 2.0 for n in (
        "calibration_report.json", "fill_quality_report.json", "ai_signal_study.json",
        "ai_ablation.json", "weight_suggestion.json", "growth_observations.json", "experiment_report.json")})
    health = build_nightly_health(tmp_path)
    assert health["status"] == "ok"
    assert health["stale_reports"] == []


def test_stale_report_flags_attention(tmp_path):
    _seed_reports(tmp_path, {"calibration_report.json": 50.0})  # >30h stale; others missing
    health = build_nightly_health(tmp_path)
    assert health["status"] == "attention"
    assert "calibration_report.json" in health["stale_reports"]
    # missing reports are also stale
    assert "fill_quality_report.json" in health["stale_reports"]


def test_failed_step_flags_attention(tmp_path):
    _seed_reports(tmp_path, {n: 1.0 for n in (
        "calibration_report.json", "fill_quality_report.json", "ai_signal_study.json",
        "ai_ablation.json", "weight_suggestion.json", "growth_observations.json", "experiment_report.json")})
    # nightly step_results with one failure on a run date
    rd = "2026-06-17"
    (tmp_path / "runtime" / "state" / "runs" / rd / "planner").mkdir(parents=True)  # makes it a discoverable run date
    sr = tmp_path / "runtime" / "logs" / "runs" / rd / "nightly" / "step_results.jsonl"
    sr.parent.mkdir(parents=True)
    sr.write_text("\n".join(json.dumps(r) for r in [
        {"step": "analytics calibrate", "status": "ok", "exit_code": 0, "timestamp": f"{rd}T20:01:00"},
        {"step": "growth shadow", "status": "fail", "exit_code": 1, "timestamp": f"{rd}T20:05:00"},
    ]) + "\n", encoding="utf-8")

    health = build_nightly_health(tmp_path)
    assert health["status"] == "attention"
    assert health["failed_steps"] == ["growth shadow"]
    assert health["last_nightly_run_date"] == rd


def test_write_persists(tmp_path):
    out = write_nightly_health(tmp_path)
    assert out.exists()
    assert json.loads(out.read_text(encoding="utf-8"))["status"] == "attention"  # nothing seeded -> all missing
