from __future__ import annotations

import json
from pathlib import Path

from trading_agent.analytics.retention import (
    apply_retention,
    plan_retention,
    write_retention_report,
)


def _make_run(root: Path, run_date: str, *, market_feed_bytes: int = 1000,
              with_analysis_inputs: bool = True) -> None:
    """Create a run with a big market_feed/ dir + small analysis inputs."""
    state = root / "runtime" / "state" / "runs" / run_date
    # big prunable artifact
    mf = state / "market_feed" / "ohlcv" / "NVDA"
    mf.mkdir(parents=True, exist_ok=True)
    (mf / "daily.json").write_text("x" * market_feed_bytes, encoding="utf-8")
    (state / "market_feed" / "charts" / "NVDA").mkdir(parents=True, exist_ok=True)
    (state / "market_feed" / "charts" / "NVDA" / "daily.png").write_text("p" * market_feed_bytes, encoding="utf-8")
    if with_analysis_inputs:
        (state / "planner").mkdir(parents=True, exist_ok=True)
        (state / "planner" / "candidate_scores.json").write_text('{"symbols": {}}', encoding="utf-8")
        (state / "run_manifest.json").write_text('{"run_date": "%s"}' % run_date, encoding="utf-8")


def test_recent_runs_kept_old_runs_pruned():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _make_run(root, "2026-01-01")  # old
        _make_run(root, "2026-06-15")  # recent
        plan = plan_retention(root, keep_days=60, today="2026-06-18")

        prune_dates = [r["run_date"] for r in plan["prune_runs"]]
        assert "2026-01-01" in prune_dates
        assert "2026-06-15" not in prune_dates
        assert plan["total_reclaim_bytes"] > 0


def test_dry_run_deletes_nothing():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _make_run(root, "2026-01-01")
        out, report = write_retention_report(root, keep_days=60, apply=False, today="2026-06-18")

        assert report["mode"] == "dry_run"
        assert "applied" not in report
        # market_feed still on disk
        assert (root / "runtime" / "state" / "runs" / "2026-01-01" / "market_feed").exists()


def test_apply_prunes_only_market_feed_keeps_analysis_inputs():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _make_run(root, "2026-01-01")
        plan = plan_retention(root, keep_days=60, today="2026-06-18")
        result = apply_retention(plan)

        assert result["removed_dirs"] == 1
        assert result["reclaimed_bytes"] > 0
        state = root / "runtime" / "state" / "runs" / "2026-01-01"
        # big artifact gone
        assert not (state / "market_feed").exists()
        # analysis inputs preserved -> calibration/replay still runnable
        assert (state / "planner" / "candidate_scores.json").exists()
        assert (state / "run_manifest.json").exists()


def test_already_pruned_run_not_listed_again():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _make_run(root, "2026-01-01")
        first = plan_retention(root, keep_days=60, today="2026-06-18")
        apply_retention(first)
        second = plan_retention(root, keep_days=60, today="2026-06-18")
        assert second["prune_run_count"] == 0  # nothing left to prune


def test_no_runs_old_enough():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _make_run(root, "2026-06-17")
        plan = plan_retention(root, keep_days=60, today="2026-06-18")
        assert plan["prune_run_count"] == 0
        assert plan["total_reclaim_bytes"] == 0


def test_write_report_emits_json_and_md():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _make_run(root, "2026-01-01")
        out, report = write_retention_report(root, keep_days=60, apply=False, today="2026-06-18")
        assert out.exists() and out.name == "retention_report.json"
        md = out.with_suffix(".md")
        assert md.exists()
        assert "DRY-RUN" in md.read_text(encoding="utf-8")
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["prune_run_count"] == 1


def test_apply_via_write_report_records_deletion():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _make_run(root, "2026-01-01")
        out, report = write_retention_report(root, keep_days=60, apply=True, today="2026-06-18")
        assert report["mode"] == "applied"
        assert report["applied"]["removed_dirs"] == 1
        assert not (root / "runtime" / "state" / "runs" / "2026-01-01" / "market_feed").exists()
