from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.time import PT
from trading_agent.core.config import load_runtime_config
from trading_agent.core.time import pt_date_string
from trading_agent.paper.broker import record_paper_day_end
from trading_agent.prompts.codex import run_codex_prompt


def _is_weekday_pt() -> bool:
    return datetime.now(tz=PT).weekday() < 5


def run_postmarket_pipeline(*, dry_run: bool) -> int:
    del dry_run
    agent_root = Path.cwd()
    paths = build_runtime_paths(agent_root)
    if not _is_weekday_pt() and os.environ.get("ALLOW_WEEKEND_RUN", "0") != "1":
        return 0
    status = run_codex_prompt("postmarket", agent_root, paths.prompts_dir / "postmarket" / "summary.txt")
    runtime = load_runtime_config(agent_root)
    if runtime.trading_mode == "paper":
        record_paper_day_end(agent_root, run_date=pt_date_string())
    return status
