from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import write_json

# H7 — fundamental quality layer (ChatGPT Phase 7). DELIBERATELY NOT a buy signal: it only produces
# quality flags for use as a filter / sizing modifier / watchlist priority / holding-quality /
# risk-overlay warning. Like the H2 factor layer it is write-only advisory and does NOT feed champion
# scoring. The numeric source is best-effort yfinance fundamentals (often partial); every field is
# optional and None when unavailable, so the layer degrades gracefully until a richer source is wired.

# yfinance Ticker.info key -> our normalized field.
_FIELD_MAP = {
    "profit_margin": "profitMargins",
    "operating_margin": "operatingMargins",
    "return_on_equity": "returnOnEquity",
    "revenue_growth": "revenueGrowth",
    "debt_to_equity": "debtToEquity",
    "current_ratio": "currentRatio",
}

FundamentalProvider = Callable[[str], dict[str, Any]]


def _as_float(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # drop NaN


def normalize_fundamental(symbol: str, raw: dict[str, Any], *, asof_date: str) -> dict[str, Any]:
    """Map a raw fundamentals dict (yfinance info shape) into the normalized snapshot. Unknown keys
    are ignored; missing values stay None."""
    snapshot: dict[str, Any] = {"symbol": symbol.upper(), "asof_date": asof_date}
    for field, source_key in _FIELD_MAP.items():
        snapshot[field] = _as_float(raw.get(source_key))
    snapshot["quality_flags"] = quality_flags(snapshot)
    snapshot["suggested_use"] = "quality_warning" if snapshot["quality_flags"] else "quality_ok"
    return snapshot


def quality_flags(snapshot: dict[str, Any]) -> list[str]:
    """Quality warnings, NOT buy signals. Each flag is a reason to down-weight / size-down / watch a
    name more closely — never a reason to buy."""
    flags: list[str] = []
    pm = snapshot.get("profit_margin")
    if pm is not None and pm < 0:
        flags.append("unprofitable")
    roe = snapshot.get("return_on_equity")
    if roe is not None and roe < 0:
        flags.append("negative_roe")
    rg = snapshot.get("revenue_growth")
    if rg is not None and rg < 0:
        flags.append("revenue_declining")
    de = snapshot.get("debt_to_equity")
    if de is not None and de > 200:  # yfinance reports debt/equity as a percentage
        flags.append("high_leverage")
    cr = snapshot.get("current_ratio")
    if cr is not None and cr < 1.0:
        flags.append("weak_liquidity")
    return flags


def yfinance_fundamentals(symbol: str) -> dict[str, Any]:
    """Best-effort fundamentals from yfinance. Returns {} on any failure / no network."""
    try:
        import yfinance as yf

        info = getattr(yf.Ticker(symbol), "info", None)
        return dict(info) if isinstance(info, dict) else {}
    except Exception:
        return {}


def build_fundamental_layer(
    agent_root: Path,
    run_date: str,
    *,
    symbols: list[str],
    provider: FundamentalProvider = yfinance_fundamentals,
) -> dict[str, Any]:
    """Normalize fundamentals for `symbols` into one write-only advisory payload. Does not feed
    champion scoring. Symbols with no data still appear (all-None snapshot)."""
    snapshots = {sym.upper(): normalize_fundamental(sym, provider(sym) or {}, asof_date=run_date) for sym in symbols}
    return {
        "date": run_date,
        "asof_date": run_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": 1,
        "symbols": snapshots,
        "notes": "Fundamental quality layer (H7): write-only advisory; quality filter only, never a buy signal.",
    }


def default_fundamental_path(agent_root: Path, run_date: str) -> Path:
    return build_runtime_paths(agent_root, run_date=run_date).signals_dir / "fundamental_snapshot.json"


def build_and_write_fundamental_layer(
    agent_root: Path, run_date: str, *, symbols: list[str], provider: FundamentalProvider = yfinance_fundamentals
) -> Path:
    payload = build_fundamental_layer(agent_root, run_date, symbols=symbols, provider=provider)
    out = default_fundamental_path(agent_root, run_date)
    write_json(out, payload)
    return out
