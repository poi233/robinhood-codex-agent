from __future__ import annotations

import json
from pathlib import Path

from trading_agent.analytics.validate import (
    format_validate_markdown,
    validate_run_data,
    write_validate_report,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _seed_run_date(root: Path, run_date: str) -> None:
    """discover_run_dates scans runtime/state/runs/*, so a run date must have that dir to be seen."""
    (root / "runtime" / "state" / "runs" / run_date).mkdir(parents=True, exist_ok=True)


def _decisions_path(root: Path, run_date: str) -> Path:
    return root / "runtime" / "logs" / "runs" / run_date / "audit" / "decisions.jsonl"


def _orders_path(root: Path, run_date: str) -> Path:
    return root / "runtime" / "state" / "runs" / run_date / "paper" / "orders.jsonl"


def test_clean_data_is_ok(tmp_path):
    rd = "2026-06-15"
    _seed_run_date(tmp_path, rd)
    _write(_decisions_path(tmp_path, rd),
            json.dumps({"timestamp": f"{rd}T09:31:00", "decision": "no_trade"}) + "\n")
    _write(_orders_path(tmp_path, rd),
            json.dumps({"order_id": "p1", "symbol": "NVDA", "status": "filled"}) + "\n")

    report = validate_run_data(tmp_path)

    assert report["status"] == "ok"
    assert report["total_malformed"] == 0
    assert report["total_missing_key"] == 0
    assert report["totals"]["decisions"]["parsed"] == 1


def test_malformed_json_line_is_counted(tmp_path):
    rd = "2026-06-15"
    _seed_run_date(tmp_path, rd)
    _write(_decisions_path(tmp_path, rd),
           json.dumps({"timestamp": f"{rd}T09:31:00", "decision": "no_trade"}) + "\n"
           + "{not valid json\n"
           + "[1, 2, 3]\n")  # valid JSON but not a dict -> malformed

    report = validate_run_data(tmp_path)

    assert report["status"] == "attention"
    assert report["totals"]["decisions"]["malformed"] == 2
    assert report["totals"]["decisions"]["parsed"] == 1


def test_missing_required_key_is_counted(tmp_path):
    rd = "2026-06-15"
    _seed_run_date(tmp_path, rd)
    # decision row missing "decision"; order row missing "status"
    _write(_decisions_path(tmp_path, rd),
           json.dumps({"timestamp": f"{rd}T09:31:00"}) + "\n")
    _write(_orders_path(tmp_path, rd),
           json.dumps({"order_id": "p1", "symbol": "NVDA"}) + "\n")

    report = validate_run_data(tmp_path)

    assert report["status"] == "attention"
    assert report["total_missing_key"] == 2
    assert report["totals"]["decisions"]["missing_key_detail"] == {"decision": 1}
    assert report["totals"]["orders"]["missing_key_detail"] == {"status": 1}


def test_empty_or_absent_files_are_ok(tmp_path):
    # No run dirs at all → nothing to validate, status ok, no crash.
    report = validate_run_data(tmp_path)
    assert report["status"] == "ok"
    assert report["run_date_count"] == 0


def test_blank_lines_ignored(tmp_path):
    rd = "2026-06-15"
    _seed_run_date(tmp_path, rd)
    _write(_decisions_path(tmp_path, rd),
           "\n" + json.dumps({"timestamp": "t", "decision": "no_trade"}) + "\n\n")
    report = validate_run_data(tmp_path)
    assert report["totals"]["decisions"]["lines"] == 1
    assert report["status"] == "ok"


def test_write_report_emits_json_and_md(tmp_path):
    rd = "2026-06-15"
    _seed_run_date(tmp_path, rd)
    _write(_decisions_path(tmp_path, rd), "{bad json\n")

    out, report = write_validate_report(tmp_path)

    assert out.exists()
    assert out.name == "validate_report.json"
    md = out.with_suffix(".md")
    assert md.exists()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "attention"
    # markdown lists the problem run date
    assert rd in md.read_text(encoding="utf-8")


def test_markdown_clean_state():
    report = {
        "generated_at": "2026-06-18T00:00:00+00:00", "status": "ok", "run_date_count": 1,
        "total_malformed": 0, "total_missing_key": 0,
        "totals": {"decisions": {"lines": 1, "parsed": 1, "malformed": 0, "missing_key": 0}},
        "per_run": [{"run_date": "2026-06-15", "sources": {"decisions": {"malformed": 0, "missing_key": 0}}}],
    }
    md = format_validate_markdown(report)
    assert "🟢" in md
    assert "No malformed lines" in md
