from __future__ import annotations

import json
from pathlib import Path

from trading_agent.replay.screen_eval import build_screen_eval, write_screen_eval_report


def _write_change(root: Path, rd: str, payload: dict) -> None:
    p = root / "runtime" / "screener" / rd / "universe_change.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload), encoding="utf-8")


def _bars(start_close: float, n: int = 90, step: float = 1.0) -> list[tuple[str, float]]:
    import datetime as dt

    d0 = dt.date(2026, 5, 1)
    return [((d0 + dt.timedelta(days=i)).isoformat(), start_close + i * step) for i in range(n)]


def test_insufficient_when_no_runs(tmp_path):
    report = build_screen_eval(tmp_path)
    assert report["status"] == "insufficient_data"
    assert report["reason"] == "no_screener_runs"


def test_added_demoted_and_ic_computed(tmp_path):
    rd = "2026-05-03"
    # screen_scores monotonic with realized return: HI>MID>LO → positive Rank IC (needs ≥3 samples)
    _write_change(tmp_path, rd, {
        "added": [{"symbol": "WIN", "factor_score": 9.0}, {"symbol": "LOSE", "factor_score": 1.0}],
        "demoted": ["DUMP"],
        "screen_scores": {"HI": 9.0, "MID": 5.0, "LO": 1.0},
    })

    steps = {"WIN": 2.0, "LOSE": 0.1, "DUMP": -1.0, "SPY": 0.4, "HI": 2.0, "MID": 1.0, "LO": 0.1}

    def loader(symbol, start, end):
        return _bars(100.0 if symbol != "SPY" else 400.0, step=steps[symbol])

    report = build_screen_eval(tmp_path, horizons=(5, 21), price_loader=loader)
    assert report["status"] == "ok"
    assert report["added_count"] == 2
    assert report["demoted_count"] == 1
    # added mean return at 5d is positive
    assert report["added"]["5"]["mean_return"] > 0
    # higher screen_score → higher realized return → positive Rank IC
    assert report["screen_score_ic"]["5"]["ic"] is not None
    assert report["screen_score_ic"]["5"]["ic"] > 0
    assert report["screen_score_ic"]["5"]["n"] == 3


def test_write_report_emits_json_and_md_even_when_empty(tmp_path):
    json_path, md_path = write_screen_eval_report(tmp_path)
    assert json.loads(json_path.read_text())["status"] == "insufficient_data"
    assert "选股有效性报告" in md_path.read_text(encoding="utf-8")
