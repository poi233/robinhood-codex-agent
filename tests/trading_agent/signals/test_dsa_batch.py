from __future__ import annotations

import json
from pathlib import Path

from trading_agent.signals.dsa import run_parallel_dsa_scan


def _write_repo_skeleton(root: Path) -> None:
    (root / "src" / "config").mkdir(parents=True)
    (root / "src" / "prompts" / "signals").mkdir(parents=True)
    (root / "src" / "config" / "universe.txt").write_text("NVDA\nAVGO\nMDB\n", encoding="utf-8")
    (root / "src" / "prompts" / "signals" / "dsa_scan_batch.txt").write_text("batch prompt\n", encoding="utf-8")
    (root / "src" / "prompts" / "signals" / "dsa_scan.txt").write_text("fallback prompt\n", encoding="utf-8")


def _symbol_signal(symbol: str, score: int, bias: str = "candidate") -> dict[str, object]:
    return {
        "dsa_score": score,
        "bias": bias,
        "primary_theme": "ai_semiconductors",
        "strategy_matches": ["bull_trend"],
        "setup": "reclaim",
        "evidence_summary": f"{symbol} evidence",
        "risk_flags": [],
        "reject_reasons": [],
        "confidence": "medium",
        "data_quality": "ok",
        "suggested_premarket_use": "promote" if bias != "blocked" else "block",
    }


def _batch_payload(symbols: list[str], batch_id: str) -> dict[str, object]:
    symbol_signals = {
        symbol: _symbol_signal(symbol, 90 if symbol == "NVDA" else 80 if symbol == "AVGO" else 30, "blocked" if symbol == "MDB" else "candidate")
        for symbol in symbols
    }
    return {
        "date": "2026-06-14",
        "generated_at": "2026-06-14T05:30:00-07:00",
        "batch": {"id": batch_id, "index": int(batch_id), "count": 2, "symbols": symbols},
        "source": {"name": "codex_dsa_signal_layer", "mode": "strategy_signal_batch_only"},
        "data_status": {"quotes": "ok", "news": "partial", "historicals": "ok", "wash_sale_blocks": "missing"},
        "market_phase": "risk_on",
        "theme_scores": {
            "ai_semiconductors": 80,
            "ai_data_center_infrastructure": 40,
            "cpo_photonics_interconnect": 10,
            "space_defense_autonomy": 0,
            "nuclear_power_grid": 0,
            "broad_beta": 50,
        },
        "selected_candidates": [symbol for symbol, signal in symbol_signals.items() if signal["bias"] != "blocked"],
        "blocked_symbols": [symbol for symbol, signal in symbol_signals.items() if signal["bias"] == "blocked"],
        "symbol_signals": symbol_signals,
        "notes": "ok",
    }


def test_parallel_dsa_scan_splits_batches_and_merges_payload(tmp_path: Path, monkeypatch) -> None:
    _write_repo_skeleton(tmp_path)
    monkeypatch.setenv("RUN_DATE_PT", "2026-06-14")
    monkeypatch.setenv("DSA_BATCH_SIZE", "2")
    monkeypatch.setenv("DSA_MAX_WORKERS", "2")
    calls: list[str] = []

    def fake_runner(run_kind: str, _agent_root: Path, _prompt_file: Path, *, runtime_overrides: dict[str, str] | None = None) -> int:
        assert runtime_overrides is not None
        calls.append(run_kind)
        symbols = runtime_overrides["DSA_BATCH_SYMBOLS"].split(",")
        output_path = Path(runtime_overrides["DSA_BATCH_OUTPUT_PATH"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(_batch_payload(symbols, runtime_overrides["DSA_BATCH_ID"])), encoding="utf-8")
        return 0

    run_parallel_dsa_scan(tmp_path, prompt_runner=fake_runner)

    final_path = tmp_path / "runtime" / "state" / "runs" / "2026-06-14" / "signals" / "dsa_signals.json"
    final_payload = json.loads(final_path.read_text(encoding="utf-8"))
    assert sorted(calls) == ["dsa_premarket_scan_batch_001", "dsa_premarket_scan_batch_002"]
    assert final_payload["selected_candidates"] == ["NVDA", "AVGO"]
    assert final_payload["blocked_symbols"] == ["MDB"]
    assert final_payload["data_status"]["news"] == "partial"

    decisions_path = tmp_path / "runtime" / "logs" / "runs" / "2026-06-14" / "decisions.jsonl"
    decisions = [json.loads(line) for line in decisions_path.read_text(encoding="utf-8").splitlines()]
    assert len(decisions) == 1
    assert decisions[0]["decision"] == "dsa_signals_generated"


def test_parallel_dsa_scan_writes_partial_payload_when_batch_fails(tmp_path: Path, monkeypatch) -> None:
    _write_repo_skeleton(tmp_path)
    monkeypatch.setenv("RUN_DATE_PT", "2026-06-14")
    monkeypatch.setenv("DSA_BATCH_SIZE", "2")
    monkeypatch.setenv("DSA_MAX_WORKERS", "2")

    def fake_runner(run_kind: str, _agent_root: Path, _prompt_file: Path, *, runtime_overrides: dict[str, str] | None = None) -> int:
        assert runtime_overrides is not None
        if run_kind.endswith("_002"):
            return 42
        symbols = runtime_overrides["DSA_BATCH_SYMBOLS"].split(",")
        output_path = Path(runtime_overrides["DSA_BATCH_OUTPUT_PATH"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(_batch_payload(symbols, runtime_overrides["DSA_BATCH_ID"])), encoding="utf-8")
        return 0

    run_parallel_dsa_scan(tmp_path, prompt_runner=fake_runner)

    final_path = tmp_path / "runtime" / "state" / "runs" / "2026-06-14" / "signals" / "dsa_signals.json"
    final_payload = json.loads(final_path.read_text(encoding="utf-8"))
    assert final_payload["selected_candidates"] == ["NVDA", "AVGO"]
    assert final_payload["blocked_symbols"] == ["MDB"]
    assert final_payload["symbol_signals"]["MDB"]["data_quality"] == "failed"
    assert final_payload["data_status"]["quotes"] == "partial"

    decisions_path = tmp_path / "runtime" / "logs" / "runs" / "2026-06-14" / "decisions.jsonl"
    decisions = [json.loads(line) for line in decisions_path.read_text(encoding="utf-8").splitlines()]
    assert decisions[0]["decision"] == "dsa_signals_partial"
