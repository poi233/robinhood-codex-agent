from __future__ import annotations

import os
import subprocess
from pathlib import Path

from trading_agent.core.run_history import append_run_output_log, append_stage_log
from trading_agent.core.time import pt_date_string
from trading_agent.prompts.runtime_block import build_runtime_block


def run_codex_prompt(run_kind: str, agent_root: Path, prompt_file: Path) -> int:
    if not prompt_file.exists():
        raise FileNotFoundError(f"missing prompt file: {prompt_file}")

    dry_run = os.environ.get("CODEX_EXEC_DRY_RUN", "0") == "1"
    prompt_text = build_runtime_block(run_kind, agent_root) + prompt_file.read_text(encoding="utf-8")
    if dry_run:
        append_stage_log(
            agent_root,
            pt_date_string(),
            run_kind,
            "skipped",
            "CODEX_EXEC_DRY_RUN=1; prompt execution skipped.",
            details={"prompt_file": str(prompt_file)},
        )
        return 0

    codex_bin = os.environ.get("CODEX_BIN", "codex")
    model = os.environ.get("CODEX_MODEL", "gpt-5.5")
    timeout_sec = int(os.environ.get("CODEX_EXEC_TIMEOUT_SEC", "3600"))
    try:
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
            capture_output=True,
            check=False,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired:
        append_stage_log(
            agent_root,
            pt_date_string(),
            run_kind,
            "failed",
            f"Codex prompt timed out after {timeout_sec} seconds.",
            details={"prompt_file": str(prompt_file), "timeout_seconds": timeout_sec},
        )
        return 124
    run_date = pt_date_string()
    append_run_output_log(agent_root, run_date, run_kind, "stdout", result.stdout)
    append_run_output_log(agent_root, run_date, run_kind, "stderr", result.stderr)
    return result.returncode
