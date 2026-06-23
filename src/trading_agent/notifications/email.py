from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Mapping, Sequence

from trading_agent.core.context import RuntimePaths, build_runtime_paths
from trading_agent.core.io import write_json
from trading_agent.core.run_history import append_stage_log
from trading_agent.core.time import pt_now
from trading_agent.prompts.codex import run_codex_prompt


def _recipient() -> str:
    return os.environ.get("TRADE_NOTIFY_EMAIL", "").strip()


def _read_send_result(result_path: Path) -> dict[str, object] | None:
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    if not isinstance(result, dict):
        return None
    sent = result.get("sent") is True
    message_id = result.get("message_id")
    if not sent or not isinstance(message_id, str) or not message_id.strip():
        return None
    return result


def _stderr_size(paths: RuntimePaths, run_kind: str) -> int:
    stderr_path = paths.run_logs_dir / "outputs" / "stderr" / f"{run_kind}.log"
    try:
        return stderr_path.stat().st_size
    except OSError:
        return 0


def _is_retryable_mcp_failure(paths: RuntimePaths, run_kind: str, *, start_offset: int) -> bool:
    stderr_path = paths.run_logs_dir / "outputs" / "stderr" / f"{run_kind}.log"
    try:
        with stderr_path.open("r", encoding="utf-8") as handle:
            handle.seek(start_offset)
            stderr = handle.read()
    except OSError:
        return False
    retryable_markers = (
        "failed to get client",
        "handshaking with MCP server failed",
        "Transport channel closed",
        "Deserialize error",
    )
    return any(marker in stderr for marker in retryable_markers)


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
    result_path = paths.run_state_dir / "notifications" / f"{safe_tag}.send_result.json"
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

    run_kind = f"email_notification_{safe_tag}"
    runtime_overrides = {
        "TRADE_NOTIFY_EMAIL": recipient,
        "TRADE_NOTIFY_PAYLOAD_PATH": str(payload_path),
        "TRADE_NOTIFY_RESULT_PATH": str(result_path),
        "TRADE_NOTIFY_SUBJECT": subject,
        "TRADE_NOTIFY_EVENT_TAG": event_tag,
        "TRADE_NOTIFY_GMAIL_LABEL": gmail_label,
    }
    result_path.unlink(missing_ok=True)
    stderr_offset = _stderr_size(paths, run_kind)
    status = run_codex_prompt(
        run_kind,
        agent_root,
        paths.prompts_dir / "notifications" / "trade_email.txt",
        runtime_overrides=runtime_overrides,
    )
    result = _read_send_result(result_path)
    if result is None and _is_retryable_mcp_failure(paths, run_kind, start_offset=stderr_offset):
        result_path.unlink(missing_ok=True)
        status = run_codex_prompt(
            run_kind,
            agent_root,
            paths.prompts_dir / "notifications" / "trade_email.txt",
            runtime_overrides=runtime_overrides,
        )
        result = _read_send_result(result_path)
    if status != 0 or result is None:
        append_stage_log(
            agent_root,
            paths.run_date,
            "email_notification",
            "failed",
            f"email notification failed for {event_tag}",
            details={"payload_path": str(payload_path), "result_path": str(result_path), "status": status},
        )
        return False
    append_stage_log(
        agent_root,
        paths.run_date,
        "email_notification",
        "completed",
        f"email notification sent for {event_tag}",
        details={
            "payload_path": str(payload_path),
            "result_path": str(result_path),
            "message_id": result["message_id"],
        },
    )
    return True
