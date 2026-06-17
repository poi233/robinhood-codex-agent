from __future__ import annotations

import os
import subprocess
import shutil
from pathlib import Path
from typing import Mapping

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.run_history import append_prompt_progress_log, append_run_output_log, append_stage_log
from trading_agent.prompts.runtime_block import build_runtime_block


def run_codex_prompt(
    run_kind: str,
    agent_root: Path,
    prompt_file: Path,
    *,
    runtime_overrides: Mapping[str, str] | None = None,
) -> int:
    if not prompt_file.exists():
        raise FileNotFoundError(f"missing prompt file: {prompt_file}")

    run_date = build_runtime_paths(agent_root).run_date
    dry_run = os.environ.get("CODEX_EXEC_DRY_RUN", "0") == "1"
    prompt_text = build_runtime_block(run_kind, agent_root, overrides=runtime_overrides) + prompt_file.read_text(
        encoding="utf-8"
    )
    append_prompt_progress_log(
        agent_root,
        run_date,
        run_kind,
        "started",
        f"{run_kind} prompt started.",
        details={"prompt_file": str(prompt_file)},
    )
    if dry_run:
        append_prompt_progress_log(
            agent_root,
            run_date,
            run_kind,
            "skipped",
            "CODEX_EXEC_DRY_RUN=1; prompt execution skipped.",
            details={"prompt_file": str(prompt_file)},
        )
        append_stage_log(
            agent_root,
            run_date,
            run_kind,
            "skipped",
            "CODEX_EXEC_DRY_RUN=1; prompt execution skipped.",
            details={"prompt_file": str(prompt_file)},
        )
        return 0

    codex_bin = os.environ.get("CODEX_BIN")
    if not codex_bin:
        candidates = [
            shutil.which("codex"),
            "/opt/homebrew/bin/codex",
            "/usr/local/bin/codex",
            str(Path.home() / ".local" / "bin" / "codex"),
        ]
        for candidate in candidates:
            if candidate and Path(candidate).exists():
                codex_bin = candidate
                break
    if not codex_bin or not Path(codex_bin).exists():
        raise FileNotFoundError(
            f"missing codex executable: {codex_bin}. Set CODEX_BIN to a valid path or ensure codex is on PATH."
        )
    model = os.environ.get("CODEX_MODEL", "gpt-5.4-mini")
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
        append_prompt_progress_log(
            agent_root,
            run_date,
            run_kind,
            "timeout",
            f"Codex prompt timed out after {timeout_sec} seconds.",
            details={"prompt_file": str(prompt_file), "timeout_seconds": timeout_sec},
        )
        append_stage_log(
            agent_root,
            run_date,
            run_kind,
            "failed",
            f"Codex prompt timed out after {timeout_sec} seconds.",
            details={"prompt_file": str(prompt_file), "timeout_seconds": timeout_sec},
        )
        return 124
    append_run_output_log(agent_root, run_date, run_kind, "stdout", result.stdout)
    append_run_output_log(agent_root, run_date, run_kind, "stderr", result.stderr)
    append_prompt_progress_log(
        agent_root,
        run_date,
        run_kind,
        "completed" if result.returncode == 0 else "failed",
        f"{run_kind} prompt exited with status {result.returncode}.",
        details={"prompt_file": str(prompt_file), "returncode": result.returncode},
    )
    return result.returncode
