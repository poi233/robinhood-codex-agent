from __future__ import annotations

import json
from pathlib import Path

from trading_agent.notifications import email as email_module


def test_email_notification_noops_without_recipient(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("TRADE_NOTIFY_EMAIL", raising=False)
    monkeypatch.setenv("RUN_DATE_PT", "2026-06-14")

    sent = email_module.send_trade_email_notification(
        tmp_path,
        event_tag="PREMARKET_DONE",
        title="盘前流程完成",
        summary="ok",
    )

    assert sent is False


def test_email_notification_writes_payload_and_runs_prompt(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TRADE_NOTIFY_EMAIL", "local@example.com")
    monkeypatch.setenv("RUN_DATE_PT", "2026-06-14")
    prompt_dir = tmp_path / "src" / "prompts" / "notifications"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "trade_email.txt").write_text("send email\n", encoding="utf-8")
    report_path = tmp_path / "report.zh.md"
    report_path.write_text("# 中文报告\n\n详细内容\n", encoding="utf-8")
    calls: list[tuple[str, dict[str, str]]] = []

    def fake_runner(run_kind: str, _agent_root: Path, _prompt_file: Path, *, runtime_overrides: dict[str, str] | None = None) -> int:
        assert runtime_overrides is not None
        calls.append((run_kind, runtime_overrides))
        Path(runtime_overrides["TRADE_NOTIFY_RESULT_PATH"]).write_text(
            json.dumps({"sent": True, "message_id": "gmail-123", "label_applied": True}),
            encoding="utf-8",
        )
        return 0

    monkeypatch.setattr(email_module, "run_codex_prompt", fake_runner)

    sent = email_module.send_trade_email_notification(
        tmp_path,
        event_tag="TRADE_EXECUTED",
        title="模拟盘BUY成交",
        summary="模拟盘已成交。",
        body="【盘中成交通知】\n\n【本次操作】\n已买入 NVDA。",
        report_path=report_path,
        artifacts=[tmp_path / "runtime" / "paper" / "orders.jsonl"],
        details={"symbol": "NVDA", "side": "buy"},
    )

    payload_path = tmp_path / "runtime" / "state" / "runs" / "2026-06-14" / "notifications" / "trade_executed.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    assert sent is True
    assert payload["recipient"] == "local@example.com"
    assert payload["subject"] == "[RCA][TRADE_EXECUTED][2026-06-14] 模拟盘BUY成交"
    assert payload["label"] == "trade"
    assert payload["gmail_label"] == "trade"
    assert payload["body"] == "【盘中成交通知】\n\n【本次操作】\n已买入 NVDA。"
    assert payload["report_path"] == str(report_path)
    assert payload["report_body"] == "# 中文报告\n\n详细内容\n"
    assert calls[0][0] == "email_notification_trade_executed"
    assert calls[0][1]["TRADE_NOTIFY_EMAIL"] == "local@example.com"
    assert calls[0][1]["TRADE_NOTIFY_GMAIL_LABEL"] == "trade"
    assert calls[0][1]["TRADE_NOTIFY_RESULT_PATH"].endswith("trade_executed.send_result.json")


def test_email_notification_fails_when_prompt_exits_zero_without_send_receipt(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TRADE_NOTIFY_EMAIL", "local@example.com")
    monkeypatch.setenv("RUN_DATE_PT", "2026-06-14")
    prompt_dir = tmp_path / "src" / "prompts" / "notifications"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "trade_email.txt").write_text("send email\n", encoding="utf-8")
    monkeypatch.setattr(email_module, "run_codex_prompt", lambda *_args, **_kwargs: 0)

    sent = email_module.send_trade_email_notification(
        tmp_path,
        event_tag="POSTMARKET_DONE",
        title="盘后流程完成",
        summary="ok",
    )

    assert sent is False


def test_email_notification_retries_once_for_new_mcp_handshake_failure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TRADE_NOTIFY_EMAIL", "local@example.com")
    monkeypatch.setenv("RUN_DATE_PT", "2026-06-14")
    prompt_dir = tmp_path / "src" / "prompts" / "notifications"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "trade_email.txt").write_text("send email\n", encoding="utf-8")
    calls = 0

    def fake_runner(run_kind: str, _agent_root: Path, _prompt_file: Path, *, runtime_overrides: dict[str, str] | None = None) -> int:
        nonlocal calls
        calls += 1
        assert runtime_overrides is not None
        if calls == 1:
            stderr_path = tmp_path / "runtime" / "logs" / "runs" / "2026-06-14" / "outputs" / "stderr" / f"{run_kind}.log"
            stderr_path.parent.mkdir(parents=True, exist_ok=True)
            stderr_path.write_text("handshaking with MCP server failed\n", encoding="utf-8")
        else:
            Path(runtime_overrides["TRADE_NOTIFY_RESULT_PATH"]).write_text(
                json.dumps({"sent": True, "message_id": "gmail-456", "label_applied": True}),
                encoding="utf-8",
            )
        return 0

    monkeypatch.setattr(email_module, "run_codex_prompt", fake_runner)

    sent = email_module.send_trade_email_notification(
        tmp_path,
        event_tag="POSTMARKET_DONE",
        title="盘后流程完成",
        summary="ok",
    )

    assert sent is True
    assert calls == 2


def test_trade_email_prompt_requires_exact_body_and_trade_label() -> None:
    prompt = Path("src/prompts/notifications/trade_email.txt").read_text(encoding="utf-8")

    assert "payload.body" in prompt
    assert "TRADE_NOTIFY_GMAIL_LABEL" in prompt
    assert "TRADE_NOTIFY_RESULT_PATH" in prompt
    assert '"message_id"' in prompt
    assert "trade" in prompt
    assert "发送后" in prompt
    assert "标签" in prompt
