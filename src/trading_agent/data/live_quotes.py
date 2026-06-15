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
        period="1d",
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
        latest = frame.dropna(how="all").tail(1)
        if latest.empty:
            return []
        row = latest.iloc[0]
        timestamp = latest.index[-1]
        quotes.append(
            {
                "symbol": symbol,
                "price": float(row["Close"]),
                "previous_close": float(row["Close"]),
                "timestamp": timestamp.isoformat(),
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
        quotes.append(
            {
                "symbol": symbol,
                "price": float(series.iloc[-1]),
                "previous_close": float(series.iloc[-1]),
                "timestamp": series.index[-1].isoformat(),
                "is_fresh": True,
                "source": "yfinance_live",
            }
        )
    return quotes
