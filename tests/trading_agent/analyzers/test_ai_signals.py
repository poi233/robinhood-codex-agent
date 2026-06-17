from __future__ import annotations

import json
from pathlib import Path

from trading_agent.analyzers.ai_signals import build_ai_signal_layer, build_and_write_ai_signal_layer
from trading_agent.core.context import build_runtime_paths


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _seed(agent_root: Path, run_date: str) -> None:
    paths = build_runtime_paths(agent_root, run_date=run_date)
    _write(paths.kronos_signals_path, {"date": run_date, "symbols": {
        "NVDA": {"direction_bias": "bullish", "confidence": 0.72, "setup_bias": "breakout",
                 "path_summary": "up_then_consolidate", "risk_flags": []}}})
    _write(paths.dsa_signals_path, {"date": run_date, "symbol_signals": {
        "SMH": {"bias": "candidate", "confidence": "medium", "strategy_matches": ["hot_theme"],
                "setup": "theme_leader", "suggested_premarket_use": "promote", "risk_flags": []}}})
    _write(paths.catalyst_snapshot_path, {"date": run_date, "symbols": {
        "NVDA": {"catalysts": ["launch"], "risk_flags": [], "earnings_risk": "none", "data_quality": "ok"}}})


def test_build_ai_signal_layer_normalizes_all_three_layers(tmp_path):
    _seed(tmp_path, "2026-06-17")
    payload = build_ai_signal_layer(tmp_path, "2026-06-17")

    assert payload["asof_date"] == "2026-06-17"
    assert len(payload["layers"]["kronos"]) == 1
    assert len(payload["layers"]["dsa"]) == 1
    assert len(payload["layers"]["catalyst"]) == 1
    assert payload["validation"]["valid_count"] == 3
    assert payload["validation"]["invalid_count"] == 0
    assert payload["layers"]["kronos"][0]["direction"] == "long"
    assert payload["layers"]["dsa"][0]["confidence"] == 0.55  # medium


def test_build_ai_signal_layer_handles_missing_artifacts(tmp_path):
    payload = build_ai_signal_layer(tmp_path, "2026-06-17")
    assert payload["validation"]["valid_count"] == 0
    assert payload["layers"] == {"dsa": [], "kronos": [], "catalyst": []}


def test_write_persists_to_ai_signals_path(tmp_path):
    _seed(tmp_path, "2026-06-17")
    out = build_and_write_ai_signal_layer(tmp_path, "2026-06-17")
    assert out.exists()
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["schema_version"] == 1
    assert written["validation"]["valid_count"] == 3


def test_every_written_envelope_passes_validation(tmp_path):
    from trading_agent.analyzers.ai_signal_schema import validate_ai_signal
    _seed(tmp_path, "2026-06-17")
    payload = build_ai_signal_layer(tmp_path, "2026-06-17")
    for layer in payload["layers"].values():
        for env in layer:
            assert validate_ai_signal(env) == []
