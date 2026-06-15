from __future__ import annotations

from pathlib import Path
from typing import Callable

from trading_agent.prompts.codex import run_codex_prompt

PromptRunner = Callable[..., int]


def run_dsa_scan(
    agent_root: Path,
    *,
    prompt_runner: PromptRunner = run_codex_prompt,
) -> None:
    prompt_file = agent_root / "src" / "prompts" / "signals" / "dsa_scan.txt"
    status = prompt_runner("dsa_premarket_scan", agent_root, prompt_file)
    if status != 0:
        raise RuntimeError("dsa prompt failed")
