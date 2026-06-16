from __future__ import annotations

import json
from pathlib import Path

from trading_agent.core.io import write_json
from trading_agent.replay.calibration import (
    build_calibration_report,
    default_calibration_report_path,
    write_calibration_report,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _seed(agent_root: Path, run_date: str, score: float) -> None:
    run_dir = agent_root / "runtime" / "state" / "runs" / run_date
    write_json(run_dir / "planner" / "candidate_scores.json", {"symbols": {
        "NVDA": {"score": score, "total_score": score, "score_status": "scored",
                 "components": {"technical": score, "kronos": 5.0}}}})
    _write_jsonl(agent_root / "runtime" / "logs" / "runs" / run_date / "audit" / "intraday_rankings.jsonl", [
        {"timestamp": f"{run_date}T09:31:00", "run_date": run_date, "symbol": "NVDA",
         "trade_readiness_score": score, "price_setup_score": score}])


def _loader(symbol, start, end):
    base = {
        "NVDA": [("2026-06-15", 100.0), ("2026-06-16", 101.0), ("2026-06-17", 103.0),
                 ("2026-06-18", 104.0), ("2026-06-19", 106.0), ("2026-06-22", 110.0)],
        "SPY": [("2026-06-15", 500.0), ("2026-06-16", 501.0), ("2026-06-17", 502.0),
                ("2026-06-18", 503.0), ("2026-06-19", 504.0), ("2026-06-22", 505.0)],
    }
    return base.get(symbol, [])


def test_build_calibration_report_structure(tmp_path):
    _seed(tmp_path, "2026-06-15", 66.0)

    report = build_calibration_report(tmp_path, horizons=(1, 3), benchmarks=("SPY",), price_loader=_loader)

    assert report["sample_size"] == 1
    assert report["horizons"] == [1, 3]
    assert "candidate_score" in report["score_buckets"]
    assert "trade_readiness_score" in report["score_buckets"]
    assert "price_setup_score" in report["score_buckets"]
    assert "1" in report["attribution"] or 1 in report["attribution"]
    assert "SPY" in report["benchmarks"]
    assert "setup_outcomes" in report


def test_write_calibration_report_emits_json_and_md(tmp_path):
    _seed(tmp_path, "2026-06-15", 66.0)

    json_path, md_path = write_calibration_report(tmp_path, horizons=(1,), benchmarks=("SPY",), price_loader=_loader)

    assert json_path == default_calibration_report_path(tmp_path)
    assert json_path.exists() and md_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert "score_buckets" in payload
    assert "Calibration" in md_path.read_text(encoding="utf-8")
