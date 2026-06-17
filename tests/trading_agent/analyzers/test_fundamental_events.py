from __future__ import annotations

from trading_agent.analyzers.events import build_event_layer, normalize_event
from trading_agent.analyzers.fundamental import build_fundamental_layer, normalize_fundamental, quality_flags


# ---- H7 fundamental ---------------------------------------------------------------------------

def test_fundamental_normalizes_and_flags_quality_issues():
    raw = {"profitMargins": -0.05, "returnOnEquity": -0.1, "revenueGrowth": -0.02,
           "debtToEquity": 250.0, "currentRatio": 0.8}
    snap = normalize_fundamental("nvda", raw, asof_date="2026-06-17")
    assert snap["symbol"] == "NVDA"
    assert snap["profit_margin"] == -0.05
    assert set(snap["quality_flags"]) == {"unprofitable", "negative_roe", "revenue_declining", "high_leverage", "weak_liquidity"}
    assert snap["suggested_use"] == "quality_warning"


def test_fundamental_healthy_company_has_no_flags():
    raw = {"profitMargins": 0.25, "returnOnEquity": 0.3, "revenueGrowth": 0.2, "debtToEquity": 40.0, "currentRatio": 2.0}
    snap = normalize_fundamental("MSFT", raw, asof_date="2026-06-17")
    assert snap["quality_flags"] == []
    assert snap["suggested_use"] == "quality_ok"


def test_fundamental_missing_data_is_none_not_crash():
    snap = normalize_fundamental("XYZ", {}, asof_date="2026-06-17")
    assert snap["profit_margin"] is None
    assert snap["quality_flags"] == []


def test_build_fundamental_layer_is_advisory_payload():
    payload = build_fundamental_layer(None, "2026-06-17", symbols=["NVDA"], provider=lambda s: {"profitMargins": 0.2})
    assert payload["schema_version"] == 1
    assert "never a buy signal" in payload["notes"]
    assert payload["symbols"]["NVDA"]["profit_margin"] == 0.2


# ---- H8 events --------------------------------------------------------------------------------

def test_event_flags_earnings_imminent_and_analyst_stance():
    raw = {"next_earnings_date": "2026-06-20", "recommendationMean": 1.8, "estimate_revision_pct": 0.03}
    snap = normalize_event("NVDA", raw, asof_date="2026-06-17")
    assert snap["days_to_earnings"] == 3
    assert "earnings_imminent" in snap["event_flags"]
    assert "analyst_bullish" in snap["event_flags"]
    assert "estimate_revised_up" in snap["event_flags"]


def test_event_bearish_analyst_and_downward_revision():
    raw = {"recommendationMean": 4.2, "estimate_revision_pct": -0.05}
    snap = normalize_event("XYZ", raw, asof_date="2026-06-17")
    assert "analyst_bearish" in snap["event_flags"]
    assert "estimate_revised_down" in snap["event_flags"]
    assert snap["days_to_earnings"] is None


def test_build_event_layer_is_advisory_payload():
    payload = build_event_layer(None, "2026-06-17", symbols=["NVDA"], provider=lambda s: {"recommendationMean": 1.5})
    assert "never an order signal" in payload["notes"]
    assert "analyst_bullish" in payload["symbols"]["NVDA"]["event_flags"]
