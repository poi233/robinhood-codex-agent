from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from trading_agent.core.time import PT
from trading_agent.prompts.codex import run_codex_prompt


def _is_weekday_pt() -> bool:
    return datetime.now(tz=PT).weekday() < 5


def run_postmarket_pipeline(*, dry_run: bool) -> int:
    del dry_run
    agent_root = Path.cwd()
    if not _is_weekday_pt() and os.environ.get("ALLOW_WEEKEND_RUN", "0") != "1":
        return 0
    return run_codex_prompt("postmarket", agent_root, agent_root / "prompts" / "postmarket_summary.txt")
