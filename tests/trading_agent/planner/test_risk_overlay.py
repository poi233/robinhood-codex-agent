from __future__ import annotations

from trading_agent.planner.risk_overlay import resolve_buying_power


def test_paper_mode_uses_paper_ledger_buying_power_not_robinhood_snapshot() -> None:
    result = resolve_buying_power(
        trading_mode="paper",
        paper_account={"cash": 400000.0, "equity": 400000.0},
        account_snapshot={"buying_power": 100.0},
        paper_starting_cash=400000.0,
    )

    assert result["buying_power"] == 400000.0
    assert result["source"] == "paper_account"
    assert result["paper_buying_power"] == 400000.0
    assert result["real_account_buying_power"] == 100.0


def test_paper_mode_falls_back_to_starting_cash_when_ledger_is_missing() -> None:
    result = resolve_buying_power(
        trading_mode="paper",
        paper_account=None,
        account_snapshot={"buying_power": 100.0},
        paper_starting_cash=400000.0,
    )

    assert result["buying_power"] == 400000.0
    assert result["source"] == "paper_starting_cash"
    assert result["paper_buying_power"] == 400000.0
    assert result["real_account_buying_power"] == 100.0


def test_live_mode_uses_robinhood_account_snapshot_buying_power() -> None:
    result = resolve_buying_power(
        trading_mode="live",
        paper_account={"cash": 400000.0},
        account_snapshot={"buying_power": 100.0},
        paper_starting_cash=400000.0,
    )

    assert result["buying_power"] == 100.0
    assert result["source"] == "robinhood_account_snapshot"
    assert result["paper_buying_power"] == 400000.0
    assert result["real_account_buying_power"] == 100.0
