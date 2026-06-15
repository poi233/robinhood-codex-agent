from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import write_json
from trading_agent.core.time import PT
from trading_agent.core.config import load_runtime_config
from trading_agent.paper.broker import record_paper_day_end
from trading_agent.prompts.codex import run_codex_prompt
from trading_agent.reporting.postmarket import build_paper_postmarket_summary


def _is_weekday_pt() -> bool:
    return datetime.now(tz=PT).weekday() < 5


def run_postmarket_pipeline(*, dry_run: bool) -> int:
    del dry_run
    agent_root = Path.cwd()
    paths = build_runtime_paths(agent_root)
    if not _is_weekday_pt() and os.environ.get("ALLOW_WEEKEND_RUN", "0") != "1":
        return 0
    runtime = load_runtime_config(agent_root)
    if runtime.trading_mode == "paper":
        record_paper_day_end(agent_root, run_date=paths.run_date)
        write_json(
            paths.paper_postmarket_summary_path,
            build_paper_postmarket_summary(
                run_date=paths.run_date,
                day_start_path=paths.paper_day_start_path,
                day_end_path=paths.paper_day_end_path,
                orders_log_path=paths.paper_orders_log_path,
                daily_usage_path=paths.daily_usage_path,
            ),
        )
    status = run_codex_prompt("postmarket", agent_root, paths.prompts_dir / "postmarket" / "summary.txt")
    return status
