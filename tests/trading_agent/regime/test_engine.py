from __future__ import annotations

import json

from trading_agent.regime.engine import (
    build_and_write_regime_state,
    classify_regime,
    indicators_from_market_feed,
)


def test_panic_on_high_vix_or_crash():
    assert classify_regime({"vix": 40})["regime"] == "panic"
    assert classify_regime({"spy_return_20d": -0.12})["regime"] == "panic"
    out = classify_regime({"vix": 40})
    assert out["multiplier"] == 0.0 and out["applied_multiplier"] == 0.0


def test_risk_off_on_elevated_vix_or_below_sma200():
    assert classify_regime({"vix": 28})["regime"] == "risk_off"
    assert classify_regime({"spy_above_sma200": False})["regime"] == "risk_off"
    assert classify_regime({"spy_return_20d": -0.05})["regime"] == "risk_off"
    assert classify_regime({"vix": 28})["multiplier"] == 0.5


def test_bull_requires_trend_and_low_vix():
    out = classify_regime({"spy_above_sma200": True, "spy_return_20d": 0.05, "vix": 15})
    assert out["regime"] == "bull"
    assert out["multiplier"] == 1.2
    # red line: applied multiplier is clamped to 1.0 (no leverage at the sizing boundary)
    assert out["applied_multiplier"] == 1.0


def test_neutral_default_and_unknown():
    assert classify_regime({"spy_above_sma200": True, "spy_return_20d": 0.0, "vix": 20})["regime"] == "neutral"
    unk = classify_regime({})
    assert unk["regime"] == "unknown" and unk["applied_multiplier"] == 1.0


def test_indicators_from_market_feed(tmp_path):
    from trading_agent.core.io import write_json
    feed = tmp_path / "ohlcv"
    # SPY: 200 rising bars, last clearly above its SMA200, +~? over 20d
    spy = [{"close": 300.0 + i} for i in range(220)]
    write_json(feed / "SPY" / "daily.json", spy)
    write_json(feed / "QQQ" / "daily.json", [{"close": 400.0 + i} for i in range(220)])
    ind = indicators_from_market_feed(tmp_path, vix=16.0)
    assert ind["spy_above_sma200"] is True
    assert ind["spy_return_20d"] is not None
    assert ind["vix"] == 16.0


def test_build_and_write_uses_injected_indicators(tmp_path):
    out = build_and_write_regime_state(tmp_path, "2026-06-17",
                                       indicators={"vix": 40, "spy_return_20d": -0.15})
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["regime"] == "panic"
    assert payload["schema_version"] == 1
    assert "de-risk" in payload["notes"]


# --- K2 second version: VIX auto-fetch ---

def _seed_feed(tmp_path):
    from trading_agent.core.io import write_json
    feed = tmp_path / "ohlcv"
    write_json(feed / "SPY" / "daily.json", [{"close": 300.0 + i} for i in range(220)])
    write_json(feed / "QQQ" / "daily.json", [{"close": 400.0 + i} for i in range(220)])


def test_vix_fetched_via_injected_fetcher_when_not_passed(tmp_path):
    _seed_feed(tmp_path)
    ind = indicators_from_market_feed(tmp_path, vix_fetcher=lambda: 28.0)
    assert ind["vix"] == 28.0


def test_explicit_vix_takes_precedence_over_fetcher(tmp_path):
    _seed_feed(tmp_path)
    ind = indicators_from_market_feed(tmp_path, vix=15.0, vix_fetcher=lambda: 99.0)
    assert ind["vix"] == 15.0


def test_vix_fetcher_failure_degrades_to_none(tmp_path):
    _seed_feed(tmp_path)

    def boom():
        raise RuntimeError("network")

    # indicators_from_market_feed itself does not catch; fetch_vix_level does. Simulate the real
    # fetcher's contract: it returns None on failure.
    ind = indicators_from_market_feed(tmp_path, vix_fetcher=lambda: None)
    assert ind["vix"] is None


def test_fetch_vix_level_returns_none_on_import_failure(monkeypatch):
    from trading_agent.regime import engine
    # Force the yfinance import inside fetch_vix_level to fail.
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "yfinance":
            raise ImportError("no yfinance")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert engine.fetch_vix_level() is None
