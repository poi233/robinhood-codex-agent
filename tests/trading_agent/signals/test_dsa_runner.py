from __future__ import annotations

from pathlib import Path

import pytest

from trading_agent.signals.dsa import run_dsa_scan


def test_run_dsa_scan_uses_single_prompt_file(tmp_path: Path) -> None:
    prompt_dir = tmp_path / "src" / "prompts" / "signals"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "dsa_scan.txt").write_text("prompt\n", encoding="utf-8")
    calls: list[tuple[str, Path]] = []

    def fake_runner(run_kind: str, agent_root: Path, prompt_file: Path) -> int:
        calls.append((run_kind, prompt_file))
        assert agent_root == tmp_path
        return 0

    run_dsa_scan(tmp_path, prompt_runner=fake_runner)

    assert calls == [("dsa_premarket_scan", prompt_dir / "dsa_scan.txt")]


def test_run_dsa_scan_raises_when_prompt_fails(tmp_path: Path) -> None:
    prompt_dir = tmp_path / "src" / "prompts" / "signals"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "dsa_scan.txt").write_text("prompt\n", encoding="utf-8")

    def fake_runner(_run_kind: str, _agent_root: Path, _prompt_file: Path) -> int:
        return 42

    with pytest.raises(RuntimeError, match="dsa prompt failed"):
        run_dsa_scan(tmp_path, prompt_runner=fake_runner)
