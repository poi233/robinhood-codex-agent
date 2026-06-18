from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from trading_agent.core.io import read_json, write_json

# K2 — quantitative market-regime engine. Replaces the LLM-set market_regime (an opinion in
# daily_plan) with a deterministic, backtestable classifier over breadth indicators, plus a position
# multiplier. First version: write-only advisory (regime_state.json) — it does NOT change sizing yet.
#
# RED LINE: when later wired into sizing, the multiplier may only be applied as min(1.0, multiplier)
# — it can de-risk (RiskOff 0.5x, Panic 0x) but the Bull 1.2x is recorded as signal strength and is
# clamped to 1.0 at the sizing boundary; the engine never introduces leverage on its own.

# regime -> position multiplier (raw; the sizing boundary clamps to <= 1.0).
_MULTIPLIER = {"bull": 1.2, "neutral": 1.0, "risk_off": 0.5, "panic": 0.0, "unknown": 1.0}


def classify_regime(indicators: dict[str, Any]) -> dict[str, Any]:
    """Deterministic regime from breadth indicators. Inputs (any may be missing -> graceful):
    spy_above_sma200 (bool), spy_return_20d (frac), qqq_return_20d (frac), vix (level).
    Missing all key inputs -> `unknown` / 1.0 (neutral, no de-risk)."""
    vix = indicators.get("vix")
    spy_ret = indicators.get("spy_return_20d")
    spy_above = indicators.get("spy_above_sma200")

    if vix is None and spy_ret is None and spy_above is None:
        regime, reasons = "unknown", ["insufficient_indicators"]
    else:
        reasons: list[str] = []
        if (vix is not None and vix >= 35) or (spy_ret is not None and spy_ret <= -0.10):
            regime = "panic"
            if vix is not None and vix >= 35:
                reasons.append(f"vix>=35 ({vix})")
            if spy_ret is not None and spy_ret <= -0.10:
                reasons.append(f"spy_20d<=-10% ({spy_ret})")
        elif (vix is not None and vix >= 25) or (spy_above is False) or (spy_ret is not None and spy_ret <= -0.03):
            regime = "risk_off"
            if vix is not None and vix >= 25:
                reasons.append(f"vix>=25 ({vix})")
            if spy_above is False:
                reasons.append("spy_below_sma200")
            if spy_ret is not None and spy_ret <= -0.03:
                reasons.append(f"spy_20d<=-3% ({spy_ret})")
        elif spy_above is True and (spy_ret is not None and spy_ret >= 0.02) and (vix is None or vix < 18):
            regime = "bull"
            reasons.append("spy_above_sma200 & spy_20d>=+2% & vix<18")
        else:
            regime = "neutral"
            reasons.append("no risk-off / bull trigger")

    raw_mult = _MULTIPLIER[regime]
    return {
        "regime": regime,
        "multiplier": raw_mult,
        "applied_multiplier": min(1.0, raw_mult),  # the value a sizing boundary may use (de-risk only)
        "reasons": reasons,
        "indicators": {"vix": vix, "spy_return_20d": spy_ret, "spy_above_sma200": spy_above,
                       "qqq_return_20d": indicators.get("qqq_return_20d")},
    }


def _bars_close(market_feed_dir: Path, symbol: str) -> list[float]:
    from trading_agent.features.factor_store import load_daily_bars

    return [float(b["close"]) for b in load_daily_bars(market_feed_dir, symbol) if isinstance(b, dict) and b.get("close") is not None]


def _vix_capture_enabled() -> bool:
    # Default on: one extra best-effort yfinance call for ^VIX completes the regime classification's
    # panic/risk_off thresholds. Flip off to keep regime SPY/QQQ-only (VIX rules degrade gracefully).
    return str(os.environ.get("ENABLE_REGIME_VIX_FETCH", "1") or "1") == "1"


def fetch_vix_level() -> float | None:
    """Best-effort latest ^VIX close from yfinance. Returns None on any failure (the regime engine
    then degrades the VIX rules gracefully). Network call — kept out of the pure classify path."""
    try:
        import yfinance as yf

        frame = yf.download(tickers="^VIX", period="5d", interval="1d",
                            auto_adjust=False, progress=False, threads=False)
        if frame is None or frame.empty:
            return None
        closes = frame["Close"]
        # yfinance may return a multi-column frame keyed by ticker.
        if hasattr(closes, "columns"):
            closes = closes.iloc[:, 0]
        series = closes.dropna()
        return float(series.values[-1]) if not series.empty else None
    except Exception:
        return None


def indicators_from_market_feed(
    market_feed_dir: Path,
    *,
    vix: float | None = None,
    vix_fetcher: Callable[[], float | None] | None = None,
) -> dict[str, Any]:
    """Derive regime indicators from the market_feed SPY/QQQ daily bars (L3 guarantees they exist).
    VIX is not in market_feed; when not passed in, best-effort fetch ^VIX (K2 second version) so the
    panic/risk_off VIX thresholds engage. The fetcher is injectable for offline tests; any failure
    leaves vix=None and the VIX rules degrade gracefully."""
    if vix is None and _vix_capture_enabled():
        fetcher = vix_fetcher or fetch_vix_level
        vix = fetcher()
    spy = _bars_close(market_feed_dir, "SPY")
    qqq = _bars_close(market_feed_dir, "QQQ")

    def _ret_20d(closes: list[float]) -> float | None:
        return round(closes[-1] / closes[-21] - 1, 4) if len(closes) >= 21 and closes[-21] else None

    spy_above_sma200 = None
    if len(spy) >= 200:
        spy_above_sma200 = spy[-1] > (sum(spy[-200:]) / 200)
    return {
        "vix": vix,
        "spy_return_20d": _ret_20d(spy),
        "qqq_return_20d": _ret_20d(qqq),
        "spy_above_sma200": spy_above_sma200,
    }


def default_regime_state_path(agent_root: Path, run_date: str) -> Path:
    from trading_agent.core.context import build_runtime_paths

    return build_runtime_paths(agent_root, run_date=run_date).planner_dir / "regime_state.json"


def build_and_write_regime_state(agent_root: Path, run_date: str, *, indicators: dict[str, Any] | None = None) -> Path:
    """Classify the regime from market_feed indicators (or injected ones) and write regime_state.json.
    Read-only w.r.t. trading; advisory artifact only."""
    from trading_agent.core.context import build_runtime_paths

    paths = build_runtime_paths(agent_root, run_date=run_date)
    if indicators is None:
        indicators = indicators_from_market_feed(paths.market_feed_dir)
    payload = {
        "date": run_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": 1,
        **classify_regime(indicators),
        "notes": "Advisory only (K2): deterministic regime + position multiplier. Not wired into "
                 "sizing yet; when wired it may only de-risk (applied_multiplier = min(1.0, multiplier)).",
    }
    out = default_regime_state_path(agent_root, run_date)
    write_json(out, payload)
    return out
