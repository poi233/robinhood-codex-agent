from __future__ import annotations

from trading_agent.planner.data_status import build_data_status_summary, normalize_layer_status


def test_market_closed_partial_is_not_provider_failure() -> None:
    result = normalize_layer_status(
        layer="dsa",
        raw_status={"quotes": "partial", "news": "ok", "historicals": "ok"},
        market_calendar={"trading_day": False, "session": "closed"},
    )

    assert result["status"] == "partial"
    assert result["reason_code"] == "market_closed"
    assert result["execution_blocking"] is True
    assert result["research_blocking"] is False


def test_failed_raw_status_is_provider_failure() -> None:
    result = normalize_layer_status(
        layer="technical",
        raw_status={"data_status": "failed"},
        market_calendar={"trading_day": True, "session": "premarket"},
    )

    assert result["status"] == "failed"
    assert result["reason_code"] == "provider_failed"
    assert result["execution_blocking"] is True
    assert result["research_blocking"] is True


def test_build_data_status_summary_collects_layer_reason_codes() -> None:
    summary = build_data_status_summary(
        run_date="2026-06-14",
        market_calendar={"data_status": "ok", "trading_day": False, "session": "closed"},
        layers={
            "dsa": {"quotes": "partial", "news": "ok", "historicals": "ok"},
            "kronos": {"data_status": "ok"},
            "technical": {"data_status": "ok", "symbols": {}},
        },
    )

    assert summary["date"] == "2026-06-14"
    assert summary["layers"]["dsa"]["reason_code"] == "market_closed"
    assert summary["layers"]["kronos"]["reason_code"] == "ok"
    assert summary["layers"]["technical"]["reason_code"] == "ok"
    assert summary["execution_blocking"] is True
    assert "dsa:market_closed" in summary["reason_codes"]
