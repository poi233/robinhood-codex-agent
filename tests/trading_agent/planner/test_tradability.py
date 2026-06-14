from __future__ import annotations

from trading_agent.planner.tradability import build_tradability_snapshot


def test_build_tradability_snapshot_marks_candidates_tradable_when_account_and_quote_are_ok() -> None:
    payload = build_tradability_snapshot(
        run_date="2026-06-14",
        candidate_snapshot={"selected_symbols": ["SMH"]},
        account_snapshot={"agentic_account_identified": True, "data_status": "ok"},
        quote_snapshot={"symbols": {"SMH": {"last_price": 619.96}}},
    )

    assert payload["data_status"] == "ok"
    assert payload["symbols"]["SMH"]["tradable"] is True
    assert payload["symbols"]["SMH"]["fractional_tradable"] is True
    assert payload["untradable_symbols"] == []


def test_build_tradability_snapshot_fails_closed_when_account_is_not_identified() -> None:
    payload = build_tradability_snapshot(
        run_date="2026-06-14",
        candidate_snapshot={"selected_symbols": ["SMH"]},
        account_snapshot={"agentic_account_identified": False, "data_status": "failed"},
        quote_snapshot={"symbols": {"SMH": {"last_price": 619.96}}},
    )

    assert payload["data_status"] == "failed"
    assert payload["symbols"]["SMH"]["tradable"] is False
    assert payload["untradable_symbols"] == ["SMH"]
