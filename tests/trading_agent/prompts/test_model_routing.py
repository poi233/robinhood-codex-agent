from __future__ import annotations

from trading_agent.prompts.codex import (
    DEFAULT_CODEX_MODEL,
    DEFAULT_CODEX_MODEL_MINI,
    resolve_codex_model,
)


def _clear_model_env(monkeypatch) -> None:
    for key in ("CODEX_MODEL", "CODEX_MODEL_MINI", "CODEX_MODEL_FORCE"):
        monkeypatch.delenv(key, raising=False)


def test_simple_run_kinds_use_mini_model(monkeypatch) -> None:
    _clear_model_env(monkeypatch)
    for run_kind in (
        "account_snapshot",
        "market_calendar",
        "quote_snapshot_core",
        "catalyst_enrichment",
        "email_notification_trade_filled",
    ):
        assert resolve_codex_model(run_kind) == DEFAULT_CODEX_MODEL_MINI


def test_thinking_run_kinds_use_full_model(monkeypatch) -> None:
    _clear_model_env(monkeypatch)
    for run_kind in (
        "technical_research",
        "final_premarket",
        "dsa_premarket_scan",
        "screener_discover",
        "intraday",
        "postmarket",
    ):
        assert resolve_codex_model(run_kind) == DEFAULT_CODEX_MODEL


def test_env_overrides_tier_defaults(monkeypatch) -> None:
    _clear_model_env(monkeypatch)
    monkeypatch.setenv("CODEX_MODEL", "custom-think")
    monkeypatch.setenv("CODEX_MODEL_MINI", "custom-mini")

    assert resolve_codex_model("final_premarket") == "custom-think"
    assert resolve_codex_model("account_snapshot") == "custom-mini"


def test_force_pins_every_run_kind_to_one_model(monkeypatch) -> None:
    _clear_model_env(monkeypatch)
    monkeypatch.setenv("CODEX_MODEL_FORCE", "pinned-model")

    assert resolve_codex_model("final_premarket") == "pinned-model"
    assert resolve_codex_model("account_snapshot") == "pinned-model"
