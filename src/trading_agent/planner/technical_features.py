from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_agent.core.io import read_json

TIMEFRAME_LABELS = ["daily", "weekly", "hourly", "intraday_15m"]


def sma(closes: list[float], period: int) -> float | None:
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def ema(closes: list[float], period: int) -> float | None:
    if len(closes) < period:
        return None
    multiplier = 2.0 / (period + 1)
    value = sum(closes[:period]) / period
    for close in closes[period:]:
        value = (close - value) * multiplier + value
    return value


def rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains = 0.0
    losses = 0.0
    window = closes[-(period + 1):]
    for prev, curr in zip(window[:-1], window[1:]):
        delta = curr - prev
        if delta >= 0:
            gains += delta
        else:
            losses -= delta
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def macd(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, float] | None:
    if len(closes) < slow + signal:
        return None
    macd_series: list[float] = []
    for end in range(slow, len(closes) + 1):
        window = closes[:end]
        fast_ema = ema(window, fast)
        slow_ema = ema(window, slow)
        if fast_ema is None or slow_ema is None:
            continue
        macd_series.append(fast_ema - slow_ema)
    if len(macd_series) < signal:
        return None
    signal_value = ema(macd_series, signal)
    if signal_value is None:
        return None
    macd_value = macd_series[-1]
    return {"macd": macd_value, "signal": signal_value, "hist": macd_value - signal_value}


def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    true_ranges: list[float] = []
    for i in range(1, len(closes)):
        high_low = highs[i] - lows[i]
        high_close = abs(highs[i] - closes[i - 1])
        low_close = abs(lows[i] - closes[i - 1])
        true_ranges.append(max(high_low, high_close, low_close))
    if len(true_ranges) < period:
        return None
    return sum(true_ranges[-period:]) / period


def find_swing_points(highs: list[float], lows: list[float], left: int = 2, right: int = 2) -> dict[str, list[float]]:
    swing_highs: list[float] = []
    swing_lows: list[float] = []
    n = len(highs)
    for i in range(left, n - right):
        window_high = highs[i - left:i + right + 1]
        if highs[i] == max(window_high):
            swing_highs.append(round(highs[i], 4))
        window_low = lows[i - left:i + right + 1]
        if lows[i] == min(window_low):
            swing_lows.append(round(lows[i], 4))
    return {"swing_highs": swing_highs[-5:], "swing_lows": swing_lows[-5:]}


def pct_return(closes: list[float], n: int) -> float | None:
    if len(closes) <= n:
        return None
    base = closes[-1 - n]
    if base == 0:
        return None
    return (closes[-1] - base) / base * 100.0


def trend_label(close: float, sma_short: float | None, sma_long: float | None) -> str:
    if sma_short is not None and sma_long is not None:
        if close > sma_short > sma_long:
            return "up"
        if close < sma_short < sma_long:
            return "down"
        return "sideways"
    if sma_short is not None:
        return "up" if close > sma_short else "down" if close < sma_short else "sideways"
    return "sideways"


def detect_flags(rows: list[dict[str, Any]], sma20: float | None) -> list[str]:
    flags: list[str] = []
    if len(rows) < 2:
        return flags
    last = rows[-1]
    prev = rows[-2]
    if last["high"] <= prev["high"] and last["low"] >= prev["low"]:
        flags.append("inside_bar")
    if prev["close"] and last["open"] > prev["close"] * 1.005:
        flags.append("gap_up")
    elif prev["close"] and last["open"] < prev["close"] * 0.995:
        flags.append("gap_down")
    if sma20 is not None and sma20 > 0 and abs(last["close"] - sma20) / sma20 <= 0.01:
        flags.append("pullback_to_sma20")
    if len(rows) >= 21:
        lookback_high = max(row["high"] for row in rows[-21:-1])
        if last["close"] > lookback_high:
            flags.append("range_breakout")
    return flags


def _load_rows(market_feed_dir: Path, symbol: str, label: str) -> list[dict[str, Any]] | None:
    path = market_feed_dir / "ohlcv" / symbol / f"{label}.json"
    if not path.exists():
        return None
    try:
        rows = read_json(path)
    except Exception:
        return None
    if not isinstance(rows, list) or not rows:
        return None
    return sorted(rows, key=lambda row: row.get("timestamp", ""))


def _compute_timeframe_features(rows: list[dict[str, Any]], *, recent_bars: int | None) -> dict[str, Any]:
    closes = [float(row["close"]) for row in rows]
    highs = [float(row["high"]) for row in rows]
    lows = [float(row["low"]) for row in rows]
    volumes = [float(row.get("volume") or 0) for row in rows]

    last_close = closes[-1]
    sma20 = sma(closes, 20)
    sma50 = sma(closes, 50)
    sma200 = sma(closes, 200)
    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)
    rsi14 = rsi(closes, 14)
    macd_value = macd(closes)
    atr14 = atr(highs, lows, closes, 14)
    swings = find_swing_points(highs, lows)

    window20 = rows[-20:] if len(rows) >= 20 else rows
    range_20d = {
        "high": max(row["high"] for row in window20),
        "low": min(row["low"] for row in window20),
    }
    high_recent = max(highs)
    low_recent = min(lows)
    dist_from_recent_high_pct = (
        (high_recent - last_close) / high_recent * 100.0 if high_recent else None
    )

    avg_volume_20 = sma(volumes, 20) if len(volumes) >= 20 else (sum(volumes) / len(volumes) if volumes else None)
    volume_surge_ratio = (
        volumes[-1] / avg_volume_20 if avg_volume_20 and avg_volume_20 > 0 else None
    )

    trend = trend_label(last_close, sma20, sma50 or sma200)

    features: dict[str, Any] = {
        "last_close": round(last_close, 4),
        "sma": {k: round(v, 4) for k, v in {"20": sma20, "50": sma50, "200": sma200}.items() if v is not None},
        "ema": {k: round(v, 4) for k, v in {"9": ema9, "21": ema21}.items() if v is not None},
        "price_vs_sma": {
            period: ("above" if last_close >= value else "below")
            for period, value in {"20": sma20, "50": sma50, "200": sma200}.items()
            if value is not None
        },
        "rsi_14": round(rsi14, 2) if rsi14 is not None else None,
        "macd": {k: round(v, 4) for k, v in macd_value.items()} if macd_value else None,
        "atr_14": round(atr14, 4) if atr14 is not None else None,
        "atr_pct": round(atr14 / last_close * 100.0, 2) if atr14 is not None and last_close else None,
        "range_20d": {k: round(v, 4) for k, v in range_20d.items()},
        "high_recent": round(high_recent, 4),
        "low_recent": round(low_recent, 4),
        "dist_from_recent_high_pct": round(dist_from_recent_high_pct, 2) if dist_from_recent_high_pct is not None else None,
        "avg_volume_20": round(avg_volume_20, 2) if avg_volume_20 is not None else None,
        "volume_surge_ratio": round(volume_surge_ratio, 2) if volume_surge_ratio is not None else None,
        "swing_highs": swings["swing_highs"],
        "swing_lows": swings["swing_lows"],
        "trend": trend,
        "flags": detect_flags(rows, sma20),
    }
    if recent_bars is not None:
        features["recent_bars"] = [
            {
                "t": row.get("timestamp"),
                "o": row.get("open"),
                "h": row.get("high"),
                "l": row.get("low"),
                "c": row.get("close"),
                "v": row.get("volume"),
            }
            for row in rows[-recent_bars:]
        ]
    return features


def _alignment(timeframes: dict[str, Any]) -> str:
    trends = [tf.get("trend") for tf in timeframes.values() if tf]
    if not trends:
        return "mixed"
    if all(t == "up" for t in trends):
        return "bullish"
    if all(t == "down" for t in trends):
        return "bearish"
    return "mixed"


def build_technical_features(
    market_feed_dir: Path,
    active_symbols: list[str],
    run_date: str,
    recent_bars: int = 30,
    benchmark: str = "SPY",
) -> dict[str, Any]:
    benchmark_daily_rows = _load_rows(market_feed_dir, benchmark, "daily")
    benchmark_closes = [float(row["close"]) for row in benchmark_daily_rows] if benchmark_daily_rows else None

    symbols_payload: dict[str, Any] = {}
    for symbol in active_symbols:
        timeframes: dict[str, Any] = {}
        loaded = 0
        for label in TIMEFRAME_LABELS:
            rows = _load_rows(market_feed_dir, symbol, label)
            if rows is None:
                continue
            loaded += 1
            timeframes[label] = _compute_timeframe_features(
                rows, recent_bars=recent_bars if label == "daily" else None
            )

        if not timeframes:
            symbols_payload[symbol] = {
                "data_quality": "failed",
                "timeframes": {},
                "multi_timeframe": {"alignment": "mixed", "rel_strength_vs_spy": {}},
            }
            continue

        rel_strength: dict[str, float] = {}
        daily_rows = _load_rows(market_feed_dir, symbol, "daily")
        if daily_rows and benchmark_closes:
            symbol_closes = [float(row["close"]) for row in daily_rows]
            for n, key in ((5, "5d"), (20, "20d"), (60, "60d")):
                sym_ret = pct_return(symbol_closes, n)
                bench_ret = pct_return(benchmark_closes, n)
                if sym_ret is not None and bench_ret is not None:
                    rel_strength[key] = round(sym_ret - bench_ret, 2)

        symbols_payload[symbol] = {
            "data_quality": "ok" if loaded == len(TIMEFRAME_LABELS) else "partial",
            "timeframes": timeframes,
            "multi_timeframe": {
                "alignment": _alignment(timeframes),
                "rel_strength_vs_spy": rel_strength,
            },
        }

    return {
        "date": run_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "benchmark": benchmark,
        "recent_bars_count": recent_bars,
        "symbols": symbols_payload,
    }
