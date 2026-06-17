from __future__ import annotations

import json
from pathlib import Path

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import write_json
from trading_agent.replay.ai_signal_study import (
    ai_signal_study_report,
    format_ai_signal_study_markdown,
    load_ai_signals,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _seed_candidate(agent_root: Path, run_date: str, symbol: str, score: float) -> None:
    run_dir = agent_root / "runtime" / "state" / "runs" / run_date
    write_json(run_dir / "planner" / "candidate_scores.json", {"symbols": {
        symbol: {"score": score, "total_score": score, "score_status": "scored", "components": {}}}})
    _write_jsonl(agent_root / "runtime" / "logs" / "runs" / run_date / "audit" / "intraday_rankings.jsonl", [
        {"timestamp": f"{run_date}T09:31:00", "run_date": run_date, "symbol": symbol,
         "trade_readiness_score": score, "price_setup_score": score}])


def _seed_ai_signals(agent_root: Path, run_date: str, layers: dict) -> None:
    paths = build_runtime_paths(agent_root, run_date=run_date)
    write_json(paths.ai_signals_path, {"date": run_date, "asof_date": run_date, "layers": layers})


def _loader(series: dict[str, list[tuple[str, float]]]):
    def loader(symbol: str, start: str, end: str) -> list[tuple[str, float]]:
        return series.get(symbol, [])
    return loader


def test_load_ai_signals_flattens_layers_with_run_date(tmp_path):
    _seed_ai_signals(tmp_path, "2026-06-15", {
        "kronos": [{"layer": "kronos", "symbol": "NVDA", "asof_date": "2026-06-15", "direction": "long",
                    "confidence": 0.7, "reason_codes": [], "warning_codes": []}],
        "dsa": [],
        "catalyst": [],
    })
    # discover_run_dates needs a run dir; the ai_signals write created the signals dir already.
    rows = load_ai_signals(tmp_path)
    assert len(rows) == 1
    assert rows[0]["run_date"] == "2026-06-15"
    assert rows[0]["layer"] == "kronos"


def test_study_joins_signals_to_forward_returns_and_scores_direction(tmp_path):
    # NVDA goes up 5% at 1d; a long kronos call should count as a directional hit.
    _seed_candidate(tmp_path, "2026-06-15", "NVDA", 70.0)
    _seed_ai_signals(tmp_path, "2026-06-15", {
        "kronos": [{"layer": "kronos", "symbol": "NVDA", "asof_date": "2026-06-15", "direction": "long",
                    "confidence": 0.8, "reason_codes": ["setup:breakout"], "warning_codes": []}],
        "dsa": [], "catalyst": [],
    })
    loader = _loader({"NVDA": [("2026-06-15", 100.0), ("2026-06-16", 105.0)],
                      "SPY": [("2026-06-15", 400.0), ("2026-06-16", 401.0)]})

    report = ai_signal_study_report(tmp_path, horizons=(1,), price_loader=loader)

    assert report["matched_count"] == 1
    kronos = report["layers"]["kronos"]
    assert kronos["signal_count"] == 1
    assert kronos["directional_accuracy"] == 1.0  # long call, price rose
    assert kronos["confidence_calibration"]["1"]  # has at least one bucket


def test_study_direction_miss_lowers_accuracy(tmp_path):
    # Price falls but the call was long -> miss.
    _seed_candidate(tmp_path, "2026-06-15", "AMD", 60.0)
    _seed_ai_signals(tmp_path, "2026-06-15", {
        "kronos": [{"layer": "kronos", "symbol": "AMD", "asof_date": "2026-06-15", "direction": "long",
                    "confidence": 0.6, "reason_codes": [], "warning_codes": []}],
        "dsa": [], "catalyst": [],
    })
    loader = _loader({"AMD": [("2026-06-15", 100.0), ("2026-06-16", 95.0)],
                      "SPY": [("2026-06-15", 400.0), ("2026-06-16", 401.0)]})
    report = ai_signal_study_report(tmp_path, horizons=(1,), price_loader=loader)
    assert report["layers"]["kronos"]["directional_accuracy"] == 0.0


def test_study_empty_when_no_signals(tmp_path):
    report = ai_signal_study_report(tmp_path, horizons=(1,), price_loader=_loader({}))
    assert report["matched_count"] == 0
    md = format_ai_signal_study_markdown(report)
    assert "AI Signal Study" in md


def test_unmatched_signals_are_skipped(tmp_path):
    # AI signal for a symbol with no scored candidate -> no forward return -> not matched.
    _seed_ai_signals(tmp_path, "2026-06-15", {
        "dsa": [{"layer": "dsa", "symbol": "ZZZZ", "asof_date": "2026-06-15", "direction": "long",
                 "confidence": 0.5, "reason_codes": [], "warning_codes": []}],
        "kronos": [], "catalyst": [],
    })
    report = ai_signal_study_report(tmp_path, horizons=(1,), price_loader=_loader({}))
    assert report["ai_signal_count"] == 1
    assert report["matched_count"] == 0
