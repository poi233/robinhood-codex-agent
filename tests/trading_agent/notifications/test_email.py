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
    calls: list[tuple[str, dict[str, str]]] = []

    def fake_runner(run_kind: str, _agent_root: Path, _prompt_file: Path, *, runtime_overrides: dict[str, str] | None = None) -> int:
        assert runtime_overrides is not None
        calls.append((run_kind, runtime_overrides))
        return 0

    monkeypatch.setattr(email_module, "run_codex_prompt", fake_runner)

    sent = email_module.send_trade_email_notification(
        tmp_path,
        event_tag="TRADE_EXECUTED",
        title="模拟盘BUY成交",
        summary="模拟盘已成交。",
        artifacts=[tmp_path / "runtime" / "paper" / "orders.jsonl"],
        details={"symbol": "NVDA", "side": "buy"},
    )

    payload_path = tmp_path / "runtime" / "state" / "runs" / "2026-06-14" / "notifications" / "trade_executed.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    assert sent is True
    assert payload["recipient"] == "local@example.com"
    assert payload["subject"] == "[Robinhood Codex Agent][TRADE_EXECUTED][2026-06-14] 模拟盘BUY成交"
    assert payload["label"] == "交易系统通知"
    assert calls[0][0] == "email_notification_trade_executed"
    assert calls[0][1]["TRADE_NOTIFY_EMAIL"] == "local@example.com"
