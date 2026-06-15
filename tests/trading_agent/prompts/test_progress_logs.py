from __future__ import annotations

import json
from pathlib import Path

from trading_agent.prompts.codex import run_codex_prompt
from trading_agent.prompts.runtime_block import build_runtime_block


def test_runtime_block_exposes_progress_log_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("RUN_DATE_PT", "2026-06-14")

    block = build_runtime_block("technical_research", tmp_path)

    expected = tmp_path / "runtime" / "logs" / "runs" / "2026-06-14" / "technical_research.progress.jsonl"
    assert f"PROGRESS_LOG_PATH={expected}" in block


def test_runtime_block_allows_prompt_specific_overrides(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("RUN_DATE_PT", "2026-06-14")

    block = build_runtime_block(
        "dsa_premarket_scan_batch_001",
        tmp_path,
        overrides={"DSA_BATCH_SYMBOLS": "NVDA,AVGO", "DSA_BATCH_OUTPUT_PATH": "/tmp/dsa_batch_001.json"},
    )

    assert "DSA_BATCH_SYMBOLS=NVDA,AVGO" in block
    assert "DSA_BATCH_OUTPUT_PATH=/tmp/dsa_batch_001.json" in block


def test_run_codex_prompt_records_dry_run_progress(tmp_path: Path, monkeypatch) -> None:
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("Test prompt", encoding="utf-8")
    monkeypatch.setenv("RUN_DATE_PT", "2026-06-14")
    monkeypatch.setenv("CODEX_EXEC_DRY_RUN", "1")

    status = run_codex_prompt("dsa_premarket_scan", tmp_path, prompt)

    progress_path = tmp_path / "runtime" / "logs" / "runs" / "2026-06-14" / "dsa_premarket_scan.progress.jsonl"
    records = [json.loads(line) for line in progress_path.read_text(encoding="utf-8").splitlines()]
    assert status == 0
    assert [record["status"] for record in records] == ["started", "skipped"]
    assert records[0]["run_kind"] == "dsa_premarket_scan"
