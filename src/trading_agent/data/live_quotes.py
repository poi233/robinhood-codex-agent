from __future__ import annotations

import os
from typing import Any


def _capture_book_enabled() -> bool:
    # Off by default: fetching a book is one extra (slow) call per symbol and the bar feed has none.
    # Flip on only when wired to a source that actually serves bid/ask. Absence => bid/ask stay None.
    return str(os.environ.get("LIVE_QUOTES_CAPTURE_BOOK", "0") or "0") == "1"


def _best_effort_book(symbol: str) -> tuple[float | None, float | None]:
    """Top-of-book (bid, ask) when yfinance exposes it, else (None, None). Best-effort and fully
    tolerant: the 1m-bar feed has no book, so this usually returns (None, None) and the pipeline
    keeps working on last price. Captured point-in-time for E4 fill-quality replay."""
    try:
        import yfinance as yf

        info = getattr(yf.Ticker(symbol), "fast_info", None) or {}
        bid = info.get("bid") if hasattr(info, "get") else getattr(info, "bid", None)
        ask = info.get("ask") if hasattr(info, "get") else getattr(info, "ask", None)
        bid = float(bid) if bid not in (None, 0) else None
        ask = float(ask) if ask not in (None, 0) else None
        if bid is not None and ask is not None and ask >= bid:
            return bid, ask
    except Exception:
        pass
    return None, None


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
        bid, ask = _best_effort_book(symbol) if _capture_book_enabled() else (None, None)
        quotes.append(
            {
                "symbol": symbol,
                "price": price,
                "previous_close": previous_close,
                "timestamp": series.index[-1].isoformat(),
                "is_fresh": True,
                "source": "yfinance_live",
                "bid": bid,
                "ask": ask,
            }
        )
        return quotes

    capture_book = _capture_book_enabled()
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
        bid, ask = _best_effort_book(symbol) if capture_book else (None, None)
        quotes.append(
            {
                "symbol": symbol,
                "price": price,
                "previous_close": previous_close,
                "timestamp": series.index[-1].isoformat(),
                "is_fresh": True,
                "source": "yfinance_live",
                "bid": bid,
                "ask": ask,
            }
        )
    return quotes
