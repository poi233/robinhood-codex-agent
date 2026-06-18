from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from trading_agent.core.context import build_runtime_paths, resolve_agent_root
from trading_agent.core.io import ensure_dir, write_json
from trading_agent.core.time import PT
from trading_agent.core.config import load_env_files, load_runtime_config
from trading_agent.notifications.email import send_trade_email_notification
from trading_agent.notifications.trade_email_reports import build_postmarket_email_body
from trading_agent.paper.broker import record_paper_day_end
from trading_agent.prompts.codex import run_codex_prompt
from trading_agent.reporting.postmarket import build_paper_postmarket_summary, build_paper_postmarket_zh_report
from trading_agent.strategy.manifest import build_run_manifest


def _is_weekday_pt() -> bool:
    return datetime.now(tz=PT).weekday() < 5


def run_postmarket_pipeline(*, dry_run: bool) -> int:
    del dry_run
    agent_root = resolve_agent_root()
    load_env_files(agent_root)
    if not _is_weekday_pt() and os.environ.get("ALLOW_WEEKEND_RUN", "0") != "1":
        return 0
    paths = build_runtime_paths(agent_root)
    runtime = load_runtime_config(agent_root)
    build_run_manifest(agent_root, paths.run_date)
    email_body = build_postmarket_email_body({"date": paths.run_date, "trading_mode": runtime.trading_mode})
    if runtime.trading_mode == "paper":
        record_paper_day_end(agent_root, run_date=paths.run_date)
        paper_summary = build_paper_postmarket_summary(
            run_date=paths.run_date,
            day_start_path=paths.paper_day_start_path,
            day_end_path=paths.paper_day_end_path,
            orders_log_path=paths.paper_orders_log_path,
            daily_usage_path=paths.daily_usage_path,
        )
        write_json(
            paths.paper_postmarket_summary_path,
            paper_summary,
        )
        ensure_dir(paths.postmarket_summary_path.parent)
        paths.postmarket_summary_path.write_text(build_paper_postmarket_zh_report(paper_summary), encoding="utf-8")
        email_body = build_postmarket_email_body(paper_summary)
    status = run_codex_prompt("postmarket", agent_root, paths.prompts_dir / "postmarket" / "summary.txt")
    if status == 0:
        send_trade_email_notification(
            agent_root,
            event_tag="POSTMARKET_DONE",
            title="盘后复盘完成",
            summary="盘后账户快照、模拟盘绩效汇总和复盘摘要流程已完成。",
            body=email_body,
            report_path=paths.postmarket_summary_path,
            artifacts=[
                paths.paper_postmarket_summary_path,
                paths.postmarket_summary_path,
                paths.paper_day_end_path,
                paths.paper_orders_log_path,
            ],
            details={"postmarket_prompt_status": status, "trading_mode": runtime.trading_mode},
        )
    return status
