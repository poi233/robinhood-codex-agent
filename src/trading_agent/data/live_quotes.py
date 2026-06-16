from __future__ import annotations

from typing import Any


def fetch_yfinance_live_quotes(symbols: list[str]) -> list[dict[str, Any]]:
    requested = [str(symbol).upper() for symbol in symbols if str(symbol).strip()]
    if not requested:
        return []

    try:
        import yfinance as yf
    except Exception as exc:  # pragma: no cover - import failure is environment-specific
        raise RuntimeError(f"yfinance import failed: {exc}") from exc

    frame = yf.download(
        tickers=requested,
        period="5d",
        interval="1m",
        auto_adjust=False,
        prepost=True,
        progress=False,
        threads=True,
    )
    if frame is None or frame.empty:
        return []

    quotes: list[dict[str, Any]] = []
    if len(requested) == 1:
        symbol = requested[0]
        series = frame["Close"].dropna()
        if series.empty:
            return []
        today_date = series.index[-1].date()
        prev_series = series[series.index.date < today_date]
        price = float(series.values[-1])
        previous_close = float(prev_series.values[-1]) if not prev_series.empty else price
        quotes.append(
            {
                "symbol": symbol,
                "price": price,
                "previous_close": previous_close,
                "timestamp": series.index[-1].isoformat(),
                "is_fresh": True,
                "source": "yfinance_live",
            }
        )
        return quotes

    closes = frame.get("Close")
    if closes is None:
        return []
    for symbol in requested:
        if symbol not in closes:
            continue
        series = closes[symbol].dropna()
        if series.empty:
            continue
        today_date = series.index[-1].date()
        prev_series = series[series.index.date < today_date]
        price = float(series.values[-1])
        previous_close = float(prev_series.values[-1]) if not prev_series.empty else price
        quotes.append(
            {
                "symbol": symbol,
                "price": price,
                "previous_close": previous_close,
                "timestamp": series.index[-1].isoformat(),
                "is_fresh": True,
                "source": "yfinance_live",
            }
        )
    return quotes
