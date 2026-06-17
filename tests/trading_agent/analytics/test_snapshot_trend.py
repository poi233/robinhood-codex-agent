from __future__ import annotations

import json
from pathlib import Path

from trading_agent.analytics.snapshot import build_nightly_summary, write_analysis_snapshot
from trading_agent.analytics.trend import build_trend
from trading_agent.core.io import write_json


def _seed_reports(agent_root: Path) -> None:
    a = agent_root / "runtime" / "analytics"
    a.mkdir(parents=True, exist_ok=True)
    write_json(a / "calibration_report.json", {
        "run_date_count": 4, "sample_size": 12,
        "attribution": {"1": [{"component": "technical", "n": 10, "ic": 0.18},
                              {"component": "dsa", "n": 10, "ic": -0.05}],
                        "5": [{"component": "factor_alpha", "n": 8, "ic": 0.22}]}})
    write_json(a / "experiment_report.json", {
        "champion": {"fill_rate_pct": 100.0, "no_trade_rate_pct": 0.0},
        "challengers": [{"challenger_strategy_id": "c1", "metrics": {"fill_rate_pct": 90.0, "max_drawdown": 0.05}}]})
    (a / "calibration_report.md").write_text("# Calibration\n", encoding="utf-8")


def test_nightly_summary_extracts_headline_metrics(tmp_path):
    _seed_reports(tmp_path)
    summary = build_nightly_summary(tmp_path, "2026-06-17")
    assert summary["date"] == "2026-06-17"
    assert summary["run_date_count"] == 4
    assert summary["calibration_sample_size"] == 12
    # Top component IC per horizon = highest |IC|.
    assert summary["top_component_ic"]["1"]["component"] == "technical"
    assert summary["top_component_ic"]["5"]["component"] == "factor_alpha"
    assert summary["champion"]["fill_rate_pct"] == 100.0
    assert summary["challengers"][0]["challenger_strategy_id"] == "c1"


def test_snapshot_archives_dated_copy_and_is_idempotent(tmp_path):
    _seed_reports(tmp_path)
    dest = write_analysis_snapshot(tmp_path, date="2026-06-17")
    assert (dest / "calibration_report.json").exists()
    assert (dest / "calibration_report.md").exists()
    assert (dest / "nightly_summary.json").exists()
    # Re-run overwrites the same dated dir (idempotent), and the "latest" report is untouched.
    write_analysis_snapshot(tmp_path, date="2026-06-17")
    assert (tmp_path / "runtime" / "analytics" / "calibration_report.json").exists()
    summary = json.loads((dest / "nightly_summary.json").read_text(encoding="utf-8"))
    assert summary["date"] == "2026-06-17"


def test_snapshot_handles_missing_reports(tmp_path):
    # No reports at all -> still writes a nightly_summary with None/0 fields, no crash.
    dest = write_analysis_snapshot(tmp_path, date="2026-06-17")
    summary = json.loads((dest / "nightly_summary.json").read_text(encoding="utf-8"))
    assert summary["proposal_count"] == 0
    assert summary["active_shadow_count"] == 0


def test_trend_aggregates_snapshots_into_series(tmp_path):
    for date, ic in (("2026-06-15", 0.10), ("2026-06-16", 0.14), ("2026-06-17", 0.18)):
        hist = tmp_path / "runtime" / "analytics" / "history" / date
        hist.mkdir(parents=True)
        write_json(hist / "nightly_summary.json", {
            "date": date, "fill_rate_pct": 100.0, "no_trade_rate_pct": 0.0, "proposal_count": 1,
            "active_shadow_count": 0, "calibration_sample_size": 5,
            "top_component_ic": {"1": {"component": "technical", "ic": ic}},
            "champion": {"fill_rate_pct": 100.0}, "challengers": []})

    trend = build_trend(tmp_path)
    assert trend["status"] == "ok"
    assert trend["snapshot_count"] == 3
    assert trend["dates"] == ["2026-06-15", "2026-06-16", "2026-06-17"]
    ic_series = trend["series"]["top_component_ic_1d"]
    assert [p["value"] for p in ic_series] == [0.10, 0.14, 0.18]
    assert len(trend["series"]["fill_rate_pct"]) == 3


def test_trend_insufficient_data(tmp_path):
    trend = build_trend(tmp_path)
    assert trend["status"] == "insufficient_data"
    assert trend["snapshot_count"] == 0


def test_trend_respects_since_until(tmp_path):
    for date in ("2026-06-15", "2026-06-16", "2026-06-17"):
        hist = tmp_path / "runtime" / "analytics" / "history" / date
        hist.mkdir(parents=True)
        write_json(hist / "nightly_summary.json", {"date": date, "fill_rate_pct": 100.0})
    trend = build_trend(tmp_path, since="2026-06-16")
    assert trend["dates"] == ["2026-06-16", "2026-06-17"]
