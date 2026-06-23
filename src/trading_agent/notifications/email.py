from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping, Sequence

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import write_json
from trading_agent.core.run_history import append_stage_log
from trading_agent.core.time import pt_now
from trading_agent.prompts.codex import run_codex_prompt


def _recipient() -> str:
    return os.environ.get("TRADE_NOTIFY_EMAIL", "").strip()


def send_trade_email_notification(
    agent_root: Path,
    *,
    event_tag: str,
    title: str,
    summary: str,
    body: str | None = None,
    report_path: Path | None = None,
    artifacts: Sequence[Path] | None = None,
    details: Mapping[str, object] | None = None,
) -> bool:
    recipient = _recipient()
    if not recipient:
        return False

    paths = build_runtime_paths(agent_root)
    safe_tag = "".join(char.lower() if char.isalnum() else "_" for char in event_tag).strip("_") or "event"
    payload_path = paths.run_state_dir / "notifications" / f"{safe_tag}.json"
    artifact_strings = [str(path) for path in artifacts or []]
    report_body = ""
    if report_path is not None and report_path.exists():
        report_body = report_path.read_text(encoding="utf-8")
    subject = f"[RCA][{event_tag}][{paths.run_date}] {title}"
    gmail_label = "trade"
    payload = {
        "schema_version": 1,
        "timestamp": pt_now().isoformat(),
        "date": paths.run_date,
        "recipient": recipient,
        "subject": subject,
        "label": gmail_label,
        "gmail_label": gmail_label,
        "event_tag": event_tag,
        "title": title,
        "summary": summary,
        "body": body or "",
        "report_path": str(report_path) if report_path else "",
        "report_body": report_body,
        "trading_mode": os.environ.get("TRADING_MODE", "paper"),
        "risk_tier": os.environ.get("RISK_TIER", "0"),
        "artifacts": artifact_strings,
        "details": dict(details or {}),
    }
    write_json(payload_path, payload)

    status = run_codex_prompt(
        f"email_notification_{safe_tag}",
        agent_root,
        paths.prompts_dir / "notifications" / "trade_email.txt",
        runtime_overrides={
            "TRADE_NOTIFY_EMAIL": recipient,
            "TRADE_NOTIFY_PAYLOAD_PATH": str(payload_path),
            "TRADE_NOTIFY_SUBJECT": subject,
            "TRADE_NOTIFY_EVENT_TAG": event_tag,
            "TRADE_NOTIFY_GMAIL_LABEL": gmail_label,
        },
    )
    if status != 0:
        append_stage_log(
            agent_root,
            paths.run_date,
            "email_notification",
            "failed",
            f"email notification failed for {event_tag}",
            details={"payload_path": str(payload_path), "status": status},
        )
        return False
    append_stage_log(
        agent_root,
        paths.run_date,
        "email_notification",
        "completed",
        f"email notification sent for {event_tag}",
        details={"payload_path": str(payload_path)},
    )
    return True
