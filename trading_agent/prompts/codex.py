from __future__ import annotations

import os
import subprocess
from pathlib import Path

from trading_agent.prompts.runtime_block import build_runtime_block


def run_codex_prompt(run_kind: str, agent_root: Path, prompt_file: Path) -> int:
    if not prompt_file.exists():
        raise FileNotFoundError(f"missing prompt file: {prompt_file}")

    dry_run = os.environ.get("CODEX_EXEC_DRY_RUN", "0") == "1"
    prompt_text = build_runtime_block(run_kind, agent_root) + prompt_file.read_text(encoding="utf-8")
    if dry_run:
        return 0

    codex_bin = os.environ.get("CODEX_BIN", "codex")
    model = os.environ.get("CODEX_MODEL", "gpt-5.5")
    result = subprocess.run(
        [
            codex_bin,
            "--ask-for-approval",
            "never",
            "exec",
            "--cd",
            str(agent_root),
            "--skip-git-repo-check",
            "--sandbox",
            "workspace-write",
            "-m",
            model,
            "-",
        ],
        input=prompt_text,
        text=True,
        capture_output=False,
        check=False,
    )
    return result.returncode
