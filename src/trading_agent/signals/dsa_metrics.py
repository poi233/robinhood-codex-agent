from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from trading_agent.core.io import read_json
from trading_agent.data.universe import parse_universe
from trading_agent.planner.technical_features import atr, pct_return, sma, trend_label

Downloader = Callable[[list[str], int, str], dict[str, list[dict[str, Any]]]]

RETURN_WINDOWS = ((1, "1d"), (5, "5d"), (20, "20d"), (60, "60d"))
REL_STRENGTH_WINDOWS = ((5, "5d"), (20, "20d"), (60, "60d"))


def _frame_to_rows(frame: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx, row in frame.iterrows():
        try:
            if row.isnull().all():
                continue
            close = row.get("Close")
            if close is None or close != close:  # NaN check without numpy/pandas import
                continue
            rows.append(
                {
                    "date": idx.isoformat() if hasattr(idx, "isoformat") else str(idx),
                    "open": float(row.get("Open", close) or close),
                    "high": float(row.get("High", close) or close),
                    "low": float(row.get("Low", close) or close),
                    "close": float(close),
                    "volume": float(row.get("Volume", 0) or 0),
                }
            )
        except Exception:
            continue
    return rows


def default_downloader(tickers: list[str], lookback_days: int, run_date: str) -> dict[str, list[dict[str, Any]]]:
    try:
        import yfinance as yf
    except Exception as exc:
        raise RuntimeError(f"yfinance import failed: {exc}") from exc

    end = date.fromisoformat(run_date) + timedelta(days=1)
    start = end - timedelta(days=lookback_days + 10)
    frame = yf.download(
        tickers=tickers,
        start=start.isoformat(),
        end=end.isoformat(),
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
        threads=True,
    )
    result: dict[str, list[dict[str, Any]]] = {}
    if frame is None or frame.empty:
        return result
    if len(tickers) == 1:
        result[tickers[0]] = _frame_to_rows(frame)
        return result
    for symbol in tickers:
        try:
            sub = frame[symbol]
        except Exception:
            continue
        rows = _frame_to_rows(sub)
        if rows:
            result[symbol] = rows
    return result


def mock_downloader(tickers: list[str], lookback_days: int, run_date: str) -> dict[str, list[dict[str, Any]]]:
    end = date.fromisoformat(run_date)
    result: dict[str, list[dict[str, Any]]] = {}
    for offset, symbol in enumerate(tickers):
        rows: list[dict[str, Any]] = []
        price = 100.0 + offset
        for i in range(min(lookback_days, 120)):
            day = end - timedelta(days=lookback_days - i)
            price += 0.3 + (offset % 3) * 0.05
            rows.append(
                {
                    "date": day.isoformat(),
                    "open": round(price - 0.2, 2),
                    "high": round(price + 0.3, 2),
                    "low": round(price - 0.4, 2),
                    "close": round(price, 2),
                    "volume": 1_000_000 + i * 1000,
                }
            )
        result[symbol] = rows
    return result


def _empty_symbol_payload(theme: str, liquidity: Any) -> dict[str, Any]:
    return {
        "theme": theme,
        "liquidity": liquidity,
        "last_close": None,
        "return": {key: None for _, key in RETURN_WINDOWS},
        "rel_strength_vs_spy": {},
        "trend": "sideways",
        "above_sma50": None,
        "above_sma200": None,
        "dist_from_20d_high_pct": None,
        "dist_from_52w_high_pct": None,
        "volume_surge_ratio": None,
        "atr_pct": None,
        "data_quality": "failed",
    }


def build_dsa_metrics(
    universe_file: Path,
    meta_file: Path,
    run_date: str,
    lookback_days: int = 180,
    benchmark: str = "SPY",
    mock: bool = False,
    downloader: Downloader | None = None,
) -> dict[str, Any]:
    symbols = parse_universe(universe_file)
    raw_meta = read_json(meta_file) if meta_file.exists() else {}
    meta = {k: v for k, v in raw_meta.items() if isinstance(v, dict)}

    tickers = sorted(set(symbols) | {benchmark})
    active_downloader = downloader or (mock_downloader if mock else default_downloader)
    try:
        raw_data = active_downloader(tickers, lookback_days, run_date)
    except Exception:
        raw_data = {}

    benchmark_rows = raw_data.get(benchmark)
    benchmark_closes: list[float] | None = None
    if benchmark_rows:
        sorted_bench = sorted(benchmark_rows, key=lambda row: row["date"])
        benchmark_closes = [float(row["close"]) for row in sorted_bench]

    symbol_payload: dict[str, Any] = {}
    advancers = 0
    decliners = 0
    above50_count = 0
    above200_with_data = 0
    valid_count = 0

    for symbol in symbols:
        meta_entry = meta.get(symbol, {})
        theme = meta_entry.get("theme", "unknown")
        liquidity = meta_entry.get("liquidity")
        rows = raw_data.get(symbol)
        if not rows:
            symbol_payload[symbol] = _empty_symbol_payload(theme, liquidity)
            continue

        rows_sorted = sorted(rows, key=lambda row: row["date"])
        closes = [float(row["close"]) for row in rows_sorted]
        highs = [float(row.get("high", row["close"])) for row in rows_sorted]
        lows = [float(row.get("low", row["close"])) for row in rows_sorted]
        volumes = [float(row.get("volume") or 0) for row in rows_sorted]
        last_close = closes[-1]

        sma50 = sma(closes, 50)
        sma200 = sma(closes, 200)
        trend = trend_label(last_close, sma50, sma200)

        returns = {key: pct_return(closes, n) for n, key in RETURN_WINDOWS}
        rel_strength: dict[str, float] = {}
        if benchmark_closes:
            for n, key in REL_STRENGTH_WINDOWS:
                sym_ret = pct_return(closes, n)
                bench_ret = pct_return(benchmark_closes, n)
                if sym_ret is not None and bench_ret is not None:
                    rel_strength[key] = round(sym_ret - bench_ret, 2)

        window20 = closes[-20:] if len(closes) >= 20 else closes
        high20 = max(window20)
        dist_20d_high = round((high20 - last_close) / high20 * 100.0, 2) if high20 else None

        dist_52w_high = None
        if len(closes) >= 200:
            high52 = max(closes)
            dist_52w_high = round((high52 - last_close) / high52 * 100.0, 2) if high52 else None

        atr14 = atr(highs, lows, closes, 14)
        atr_pct = round(atr14 / last_close * 100.0, 2) if atr14 is not None and last_close else None

        avg_vol20 = sma(volumes, 20) if len(volumes) >= 20 else (sum(volumes) / len(volumes) if volumes else None)
        vol_surge = round(volumes[-1] / avg_vol20, 2) if avg_vol20 and avg_vol20 > 0 else None

        above_sma50 = bool(sma50 is not None and last_close >= sma50)
        above_sma200 = bool(sma200 is not None and last_close >= sma200) if sma200 is not None else None

        quality = "ok" if len(closes) >= 60 else "partial"

        symbol_payload[symbol] = {
            "theme": theme,
            "liquidity": liquidity,
            "last_close": round(last_close, 4),
            "return": {key: (round(value, 2) if value is not None else None) for key, value in returns.items()},
            "rel_strength_vs_spy": rel_strength,
            "trend": trend,
            "above_sma50": above_sma50,
            "above_sma200": above_sma200,
            "dist_from_20d_high_pct": dist_20d_high,
            "dist_from_52w_high_pct": dist_52w_high,
            "volume_surge_ratio": vol_surge,
            "atr_pct": atr_pct,
            "data_quality": quality,
        }

        valid_count += 1
        if above_sma50:
            above50_count += 1
        if above_sma200:
            above200_with_data += 1
        day_return = returns.get("1d")
        if day_return is not None:
            if day_return > 0:
                advancers += 1
            elif day_return < 0:
                decliners += 1

    theme_groups: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for symbol, payload in symbol_payload.items():
        if payload.get("data_quality") == "failed":
            continue
        theme_groups[payload["theme"]].append((symbol, payload))

    theme_metrics: dict[str, Any] = {}
    for theme, members in theme_groups.items():
        rel20_values = [
            p["rel_strength_vs_spy"].get("20d")
            for _, p in members
            if p["rel_strength_vs_spy"].get("20d") is not None
        ]
        avg_rel20 = round(sum(rel20_values) / len(rel20_values), 2) if rel20_values else None
        pct_uptrend = round(100.0 * sum(1 for _, p in members if p["trend"] == "up") / len(members), 1)
        leaders = [
            sym
            for sym, _ in sorted(
                members, key=lambda item: item[1]["rel_strength_vs_spy"].get("20d", -999.0), reverse=True
            )[:3]
        ]
        theme_metrics[theme] = {
            "avg_rel_strength_20d": avg_rel20,
            "pct_uptrend": pct_uptrend,
            "member_count": len(members),
            "leaders": leaders,
        }

    market_breadth = {
        "pct_above_sma50": round(100.0 * above50_count / valid_count, 1) if valid_count else None,
        "pct_above_sma200": round(100.0 * above200_with_data / valid_count, 1) if valid_count else None,
        "adv_dec_ratio": round(advancers / decliners, 2) if decliners else (float(advancers) if advancers else None),
    }

    data_status = "ok" if valid_count == len(symbols) and symbols else ("partial" if valid_count > 0 else "failed")

    return {
        "date": run_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "benchmark": benchmark,
        "data_status": data_status,
        "market_breadth": market_breadth,
        "theme_metrics": theme_metrics,
        "symbols": symbol_payload,
    }
