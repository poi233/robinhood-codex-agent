#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any


TIMEFRAME_MAP = {
    "1w": {"label": "weekly", "days": 180, "step_days": 7},
    "1d": {"label": "daily", "days": 120, "step_days": 1},
    "1h": {"label": "hourly", "days": 20, "step_days": 1},
    "15m": {"label": "intraday_15m", "days": 10, "step_days": 1},
}

PLACEHOLDER_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9sY1lX8AAAAASUVORK5CYII="
)


@dataclass
class SymbolArtifacts:
    ohlcv: str
    charts: str
    news: str
    earnings: str
    filings: str
    notes: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe-file", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--timeframes", default="1w,1d,1h,15m")
    parser.add_argument("--news-limit", type=int, default=5)
    parser.add_argument("--mock", action="store_true")
    return parser.parse_args()


def parse_universe(path: Path) -> list[str]:
    seen: set[str] = set()
    symbols: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        candidate = line.strip().upper()
        if not candidate or candidate.startswith("#") or candidate in seen:
            continue
        seen.add(candidate)
        symbols.append(candidate)
    return symbols


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def json_dump(path: Path, payload: object) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_placeholder_chart(output_path: Path) -> None:
    ensure_dir(output_path.parent)
    output_path.write_bytes(PLACEHOLDER_PNG)


def write_chart(rows: list[dict[str, object]], output_path: Path, title: str) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        write_placeholder_chart(output_path)
        return

    x_values = list(range(len(rows)))
    closes = [float(row["close"]) for row in rows]
    volumes = [float(row["volume"]) for row in rows]
    ma20: list[float] = []
    ma50: list[float] = []

    for index in range(len(closes)):
        left20 = max(0, index - 19)
        left50 = max(0, index - 49)
        ma20.append(sum(closes[left20 : index + 1]) / (index - left20 + 1))
        ma50.append(sum(closes[left50 : index + 1]) / (index - left50 + 1))

    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True, height_ratios=[4, 1])
    axes[0].plot(x_values, closes, label="Close", linewidth=1.2)
    axes[0].plot(x_values, ma20, label="MA20", linewidth=1.0)
    axes[0].plot(x_values, ma50, label="MA50", linewidth=1.0)
    axes[0].set_title(title)
    axes[0].legend(loc="upper left")
    axes[1].bar(x_values, volumes)
    axes[1].set_title("Volume")
    fig.tight_layout()
    ensure_dir(output_path.parent)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def build_mock_rows(run_date: date, timeframe: str) -> list[dict[str, object]]:
    config = TIMEFRAME_MAP[timeframe]
    periods = 40
    start = run_date - timedelta(days=config["days"])
    rows: list[dict[str, object]] = []
    price = 100.0

    for index in range(periods):
        current_day = start + timedelta(days=index * config["step_days"])
        if timeframe in {"1h", "15m"}:
            timestamp = datetime.combine(current_day, time(9, 30), tzinfo=timezone.utc) + timedelta(minutes=index * 15)
        else:
            timestamp = datetime.combine(current_day, time(0, 0), tzinfo=timezone.utc)

        open_price = price + (index % 3) * 0.4
        close_price = open_price + 0.6
        high_price = close_price + 0.5
        low_price = open_price - 0.7
        volume = 1_000_000 + index * 5_000
        rows.append(
            {
                "timestamp": timestamp.isoformat(),
                "open": round(open_price, 2),
                "high": round(high_price, 2),
                "low": round(low_price, 2),
                "close": round(close_price, 2),
                "volume": volume,
            }
        )
        price += 0.8

    return rows


def fetch_live_rows(symbol: str, timeframe: str) -> list[dict[str, object]]:
    try:
        import yfinance as yf
    except Exception as exc:  # pragma: no cover - exercised only in live mode
        raise RuntimeError(f"yfinance import failed: {exc}") from exc

    config = TIMEFRAME_MAP[timeframe]
    interval = {"1w": "1wk", "1d": "1d", "1h": "60m", "15m": "15m"}[timeframe]
    period = {"1w": "3y", "1d": "1y", "1h": "60d", "15m": "30d"}[timeframe]
    frame = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=False)
    if frame.empty:
        raise RuntimeError(f"empty history for {symbol} {timeframe}")

    rows: list[dict[str, object]] = []
    for idx, row in frame.iterrows():
        rows.append(
            {
                "timestamp": idx.isoformat() if hasattr(idx, "isoformat") else str(idx),
                "open": round(float(row["Open"]), 4),
                "high": round(float(row["High"]), 4),
                "low": round(float(row["Low"]), 4),
                "close": round(float(row["Close"]), 4),
                "volume": int(row["Volume"]),
            }
        )
    return rows


def jsonable(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [jsonable(item) for item in value]
    return value


def extract_url(value: Any) -> str | None:
    if isinstance(value, dict):
        return value.get("url")
    return None


def normalize_news_item(item: dict[str, Any]) -> dict[str, object] | None:
    content = item.get("content") if isinstance(item.get("content"), dict) else item
    title = content.get("title") or item.get("title")
    if not title:
        return None

    provider = content.get("provider") if isinstance(content.get("provider"), dict) else {}
    return {
        "title": title,
        "source": provider.get("displayName") or provider.get("name") or "yfinance",
        "published_at": content.get("pubDate") or content.get("displayTime") or item.get("providerPublishTime"),
        "url": extract_url(content.get("clickThroughUrl")) or extract_url(content.get("canonicalUrl")),
    }


def build_mock_news_payload(symbol: str, run_date: str, limit: int) -> dict[str, object]:
    headline_prefix = "Mock"
    return {
        "symbol": symbol,
        "date": run_date,
        "headlines": [
            {
                "title": f"{headline_prefix} catalyst item {index + 1} for {symbol}",
                "source": "mock_source",
                "published_at": f"{run_date}T06:{index:02d}:00-0700",
            }
            for index in range(limit)
        ],
        "earnings": {"status": "ok", "next_event": None},
        "filings": {"status": "ok", "items": []},
    }


def build_live_news_payload(symbol: str, run_date: str, limit: int) -> dict[str, object]:
    try:
        import yfinance as yf
    except Exception as exc:  # pragma: no cover - exercised only in live mode
        raise RuntimeError(f"yfinance import failed: {exc}") from exc

    ticker = yf.Ticker(symbol)
    raw_news = ticker.news or []
    headlines = []
    for item in raw_news[:limit]:
        normalized = normalize_news_item(item)
        if normalized:
            headlines.append(normalized)

    try:
        calendar = jsonable(ticker.calendar or {})
    except Exception as exc:  # pragma: no cover - depends on live provider behavior
        calendar = {"status": "failed", "error": str(exc)}

    try:
        filings = jsonable(ticker.sec_filings or [])
        filing_status = "ok"
    except Exception as exc:  # pragma: no cover - depends on live provider behavior
        filings = []
        filing_status = "failed"
        filing_error = str(exc)
    else:
        filing_error = ""

    return {
        "symbol": symbol,
        "date": run_date,
        "headlines": headlines,
        "earnings": {"status": "ok", "calendar": calendar},
        "filings": {"status": filing_status, "items": filings[:limit], "error": filing_error},
    }


def build_news_payload(symbol: str, run_date: str, limit: int, mock: bool) -> dict[str, object]:
    if mock:
        return build_mock_news_payload(symbol, run_date, limit)
    return build_live_news_payload(symbol, run_date, limit)


def main() -> int:
    args = parse_args()
    run_date = date.fromisoformat(args.date)
    output_dir = Path(args.output_dir)
    universe_file = Path(args.universe_file)
    timeframes = [value.strip() for value in args.timeframes.split(",") if value.strip()]
    requested_symbols = parse_universe(universe_file)

    ensure_dir(output_dir)
    ensure_dir(output_dir / "charts")
    ensure_dir(output_dir / "ohlcv")
    ensure_dir(output_dir / "news")

    completed_symbols: list[str] = []
    failed_symbols: list[str] = []
    symbol_status: dict[str, dict[str, str]] = {}

    for symbol in requested_symbols:
        try:
            for timeframe in timeframes:
                label = TIMEFRAME_MAP[timeframe]["label"]
                rows = build_mock_rows(run_date, timeframe) if args.mock else fetch_live_rows(symbol, timeframe)
                json_dump(output_dir / "ohlcv" / symbol / f"{label}.json", rows)
                write_chart(rows, output_dir / "charts" / symbol / f"{label}.png", f"{symbol} {label}")

            news_payload = build_news_payload(symbol, args.date, args.news_limit, args.mock)
            json_dump(output_dir / "news" / f"{symbol}.json", news_payload)
            symbol_status[symbol] = SymbolArtifacts("ok", "ok", "ok", "ok", "ok").__dict__
            completed_symbols.append(symbol)
        except Exception as exc:  # pragma: no cover - live mode failure path
            symbol_status[symbol] = SymbolArtifacts("failed", "failed", "failed", "failed", "failed", str(exc)).__dict__
            failed_symbols.append(symbol)

    market_summary = {
        "date": args.date,
        "requested_symbols": requested_symbols,
        "completed_symbols": completed_symbols,
        "failed_symbols": failed_symbols,
        "summary": "mock market summary" if args.mock else "public market summary",
    }
    json_dump(output_dir / "news" / "market_summary.json", market_summary)

    manifest = {
        "date": args.date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_mode": "manual" if args.mock else "scheduled",
        "source_universe": str(universe_file),
        "requested_symbols": requested_symbols,
        "completed_symbols": completed_symbols,
        "failed_symbols": failed_symbols,
        "timeframes": timeframes,
        "sources": {
            "ohlcv": "mock" if args.mock else "yfinance",
            "news": "mock" if args.mock else "yfinance",
            "earnings": "mock" if args.mock else "yfinance",
            "filings": "mock" if args.mock else "yfinance",
        },
        "data_status": "failed" if not completed_symbols else ("partial" if failed_symbols else "ok"),
        "artifacts": {
            "charts_root": str(output_dir / "charts"),
            "ohlcv_root": str(output_dir / "ohlcv"),
            "news_root": str(output_dir / "news"),
        },
        "symbol_status": symbol_status,
        "notes": "mock artifact bundle" if args.mock else "live artifact bundle",
    }
    json_dump(output_dir / "manifest.json", manifest)
    print(json.dumps({"output_dir": str(output_dir), "data_status": manifest["data_status"]}))
    return 0 if completed_symbols else 1


if __name__ == "__main__":
    raise SystemExit(main())
