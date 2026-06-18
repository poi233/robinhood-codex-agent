from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import write_json
from trading_agent.replay.analysis import discover_run_dates

# N3 — data validation. The build path uses .get() everywhere, so a malformed JSONL line is silently
# dropped and a row missing a key field silently becomes NULL. Before real paper data accumulates,
# this read-only scan surfaces "how many lines are bad / missing a key field" so dirty data can't
# quietly poison calibration/IC. It NEVER modifies any data — pure inspection + a written report.

# Per-source JSONL files and the keys a well-formed row must have. (Path attr on RuntimePaths, then
# required keys.) Keep the required set minimal — only fields whose absence would corrupt analysis.
_JSONL_SOURCES: dict[str, tuple[str, tuple[str, ...]]] = {
    "decisions": ("decisions_log_path", ("timestamp", "decision")),
    "orders": ("paper_orders_log_path", ("order_id", "symbol", "status")),
    "paper_equity": ("paper_equity_curve_path", ("timestamp", "event")),
    "intraday_rankings": ("intraday_rankings_log_path", ("symbol",)),
}


def _scan_jsonl(path: Path, required_keys: tuple[str, ...]) -> dict[str, Any]:
    """Count, for one JSONL file: non-blank lines, valid dict rows, malformed lines (bad JSON or
    non-dict), and rows missing any required key. Read-only."""
    result = {
        "exists": path.exists(),
        "lines": 0,
        "parsed": 0,
        "malformed": 0,
        "missing_key": 0,
        "missing_key_detail": {},  # key -> count of rows missing it
    }
    if not path.exists():
        return result
    missing_detail: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        result["lines"] += 1
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            result["malformed"] += 1
            continue
        if not isinstance(payload, dict):
            result["malformed"] += 1
            continue
        result["parsed"] += 1
        missing = [k for k in required_keys if payload.get(k) in (None, "")]
        if missing:
            result["missing_key"] += 1
            for k in missing:
                missing_detail[k] = missing_detail.get(k, 0) + 1
    result["missing_key_detail"] = missing_detail
    return result


def validate_run_data(
    agent_root: Path, *, since: str | None = None, until: str | None = None
) -> dict[str, Any]:
    """Read-only scan of every run's JSONL artifacts. Reports malformed lines + rows missing key
    fields, per run-date and aggregated. status='ok' only when nothing is malformed/missing."""
    run_dates = discover_run_dates(agent_root, since_date=since, until_date=until)

    per_run: list[dict[str, Any]] = []
    totals = {
        src: {"lines": 0, "parsed": 0, "malformed": 0, "missing_key": 0, "missing_key_detail": {}}
        for src in _JSONL_SOURCES
    }
    total_malformed = 0
    total_missing = 0

    for run_date in run_dates:
        paths = build_runtime_paths(agent_root, run_date=run_date)
        run_entry: dict[str, Any] = {"run_date": run_date, "sources": {}}
        for source, (path_attr, required) in _JSONL_SOURCES.items():
            scan = _scan_jsonl(getattr(paths, path_attr), required)
            run_entry["sources"][source] = scan
            totals[source]["lines"] += scan["lines"]
            totals[source]["parsed"] += scan["parsed"]
            totals[source]["malformed"] += scan["malformed"]
            totals[source]["missing_key"] += scan["missing_key"]
            for key, count in scan["missing_key_detail"].items():
                detail = totals[source]["missing_key_detail"]
                detail[key] = detail.get(key, 0) + count
            total_malformed += scan["malformed"]
            total_missing += scan["missing_key"]
        per_run.append(run_entry)

    status = "ok" if (total_malformed == 0 and total_missing == 0) else "attention"
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": 1,
        "status": status,
        "run_date_count": len(run_dates),
        "totals": totals,
        "total_malformed": total_malformed,
        "total_missing_key": total_missing,
        "per_run": per_run,
        "note": "Read-only data validation (N3). Counts malformed JSONL lines + rows missing key "
                "fields so dirty data is visible before it poisons analysis. Modifies nothing.",
    }


def default_validate_report_path(agent_root: Path) -> Path:
    return agent_root / "runtime" / "analytics" / "validate_report.json"


def default_validate_md_path(agent_root: Path) -> Path:
    return agent_root / "runtime" / "analytics" / "validate_report.md"


def format_validate_markdown(report: dict[str, Any]) -> str:
    icon = "🟢" if report["status"] == "ok" else "🔴"
    lines = [
        "# Data Validation (N3)",
        "",
        f"_Generated {report['generated_at']}._  ·  run dates: {report['run_date_count']}",
        "",
        f"{icon} **status: {report['status']}**  ·  malformed lines: {report['total_malformed']}  ·  "
        f"rows missing a key field: {report['total_missing_key']}",
        "",
        "## Per-source totals",
        "",
        "| Source | lines | parsed | malformed | missing key |",
        "|---|---|---|---|---|",
    ]
    for source, t in report["totals"].items():
        lines.append(f"| {source} | {t['lines']} | {t['parsed']} | {t['malformed']} | {t['missing_key']} |")
    # Only list run dates that have a problem, to keep the report short.
    problem_runs = [
        r for r in report["per_run"]
        if any(s["malformed"] or s["missing_key"] for s in r["sources"].values())
    ]
    if problem_runs:
        lines += ["", "## Run dates needing attention", ""]
        for r in problem_runs:
            bad = [
                f"{src}({s['malformed']} malformed, {s['missing_key']} missing)"
                for src, s in r["sources"].items() if s["malformed"] or s["missing_key"]
            ]
            lines.append(f"- **{r['run_date']}**: " + "; ".join(bad))
    else:
        lines += ["", "_No malformed lines or missing key fields found._"]
    return "\n".join(lines) + "\n"


def write_validate_report(
    agent_root: Path, *, since: str | None = None, until: str | None = None
) -> tuple[Path, dict[str, Any]]:
    """Scan run data and write validate_report.{json,md}. Returns (json_path, report)."""
    report = validate_run_data(agent_root, since=since, until=until)
    json_path = default_validate_report_path(agent_root)
    md_path = default_validate_md_path(agent_root)
    write_json(json_path, report)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(format_validate_markdown(report), encoding="utf-8")
    return json_path, report
