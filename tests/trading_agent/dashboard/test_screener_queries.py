from __future__ import annotations

import json
from pathlib import Path

from trading_agent.dashboard import queries


def _w(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def test_screener_change_empty_when_never_run(tmp_path):
    assert queries.screener_change(tmp_path) == {}
    assert queries.list_screener_dates(tmp_path) == []


def test_screener_change_returns_latest_and_supports_picker(tmp_path):
    base = tmp_path / "runtime" / "screener"
    _w(base / "2026-06-14" / "universe_change.json", {"added": [{"symbol": "OLD"}]})
    _w(base / "2026-06-21" / "universe_change.json", {
        "added": [{"symbol": "SIVE", "factor_score": 9.0}], "demoted": ["X"],
        "applied": True, "effective_count_before": 88, "effective_count_after": 88})
    _w(base / "2026-06-21" / "status.json", {"discovered_count": 3})

    out = queries.screener_change(tmp_path)
    assert out["date"] == "2026-06-21"  # most recent
    assert out["available_dates"] == ["2026-06-21", "2026-06-14"]
    assert out["change"]["added"][0]["symbol"] == "SIVE"
    assert out["status"]["discovered_count"] == 3

    older = queries.screener_change(tmp_path, "2026-06-14")
    assert older["change"]["added"][0]["symbol"] == "OLD"


def test_active_selection_reads_and_missing_is_empty(tmp_path):
    rd = "2026-06-21"
    _w(
        tmp_path / "runtime" / "state" / "runs" / rd / "planner" / "active_selection.json",
        {"active": ["SPY", "NVDA"], "pins": ["SPY"], "from_screen": [{"symbol": "NVDA", "screen_score": 9.0}],
         "active_max": 30, "universe_size": 88},
    )
    out = queries.active_selection(tmp_path, rd)
    assert out["active"] == ["SPY", "NVDA"]
    assert out["from_screen"][0]["symbol"] == "NVDA"
    assert queries.active_selection(tmp_path, "2026-01-01") == {}
