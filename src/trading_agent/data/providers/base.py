from __future__ import annotations

from typing import Protocol


class MarketDataProvider(Protocol):
    def fetch_rows(self, symbol: str, timeframe: str) -> list[dict[str, object]]: ...

    def fetch_news(self, symbol: str, run_date: str, limit: int) -> dict[str, object]: ...
