from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import write_json

# H8 — earnings / analyst-revision event layer (ChatGPT Phase 8). DELIBERATELY NOT an independent
# order signal: it only ENHANCES the catalyst context (earnings proximity, analyst stance, surprise,
# estimate revision). Like H2/H7 it is write-only advisory and does NOT feed champion scoring. Source
# is best-effort yfinance; every field is optional and None when unavailable.

EventProvider = Callable[[str], dict[str, Any]]


def _as_float(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _days_until(date_str: Any, *, asof_date: str) -> int | None:
    try:
        target = date.fromisoformat(str(date_str)[:10])
        return (target - date.fromisoformat(asof_date)).days
    except (TypeError, ValueError):
        return None


def normalize_event(symbol: str, raw: dict[str, Any], *, asof_date: str) -> dict[str, Any]:
    """Map a raw events dict (yfinance-ish shape) into the normalized event snapshot."""
    next_earnings = raw.get("next_earnings_date") or raw.get("earningsDate")
    snapshot: dict[str, Any] = {
        "symbol": symbol.upper(),
        "asof_date": asof_date,
        "next_earnings_date": str(next_earnings)[:10] if next_earnings else None,
        "days_to_earnings": _days_until(next_earnings, asof_date=asof_date) if next_earnings else None,
        "analyst_recommendation_mean": _as_float(raw.get("recommendationMean")),
        "analyst_count": _as_float(raw.get("numberOfAnalystOpinions")),
        "earnings_surprise_pct": _as_float(raw.get("earnings_surprise_pct")),
        "estimate_revision_pct": _as_float(raw.get("estimate_revision_pct")),
    }
    snapshot["event_flags"] = event_flags(snapshot)
    return snapshot


def event_flags(snapshot: dict[str, Any]) -> list[str]:
    """Catalyst-context flags, NOT order signals. They enhance the catalyst layer; they never place
    or size a trade on their own."""
    flags: list[str] = []
    dte = snapshot.get("days_to_earnings")
    if dte is not None and 0 <= dte <= 5:
        flags.append("earnings_imminent")  # risk context — avoid fresh entries into the print
    rec = snapshot.get("analyst_recommendation_mean")
    if rec is not None and rec <= 2.0:  # yfinance: 1 = strong buy, 5 = strong sell
        flags.append("analyst_bullish")
    if rec is not None and rec >= 4.0:
        flags.append("analyst_bearish")
    rev = snapshot.get("estimate_revision_pct")
    if rev is not None and rev > 0:
        flags.append("estimate_revised_up")
    if rev is not None and rev < 0:
        flags.append("estimate_revised_down")
    return flags


def yfinance_events(symbol: str) -> dict[str, Any]:
    """Best-effort earnings/analyst data from yfinance. Returns {} on any failure / no network."""
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        info = getattr(ticker, "info", None)
        info = info if isinstance(info, dict) else {}
        out: dict[str, Any] = {
            "recommendationMean": info.get("recommendationMean"),
            "numberOfAnalystOpinions": info.get("numberOfAnalystOpinions"),
        }
        calendar = getattr(ticker, "calendar", None)
        if isinstance(calendar, dict):
            earnings = calendar.get("Earnings Date")
            if isinstance(earnings, list) and earnings:
                out["next_earnings_date"] = earnings[0]
        return out
    except Exception:
        return {}


def build_event_layer(
    agent_root: Path, run_date: str, *, symbols: list[str], provider: EventProvider = yfinance_events
) -> dict[str, Any]:
    snapshots = {sym.upper(): normalize_event(sym, provider(sym) or {}, asof_date=run_date) for sym in symbols}
    return {
        "date": run_date,
        "asof_date": run_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": 1,
        "symbols": snapshots,
        "notes": "Earnings/analyst event layer (H8): write-only advisory; enhances catalyst context, never an order signal.",
    }


def default_event_path(agent_root: Path, run_date: str) -> Path:
    return build_runtime_paths(agent_root, run_date=run_date).planner_dir / "event_snapshot.json"


def build_and_write_event_layer(
    agent_root: Path, run_date: str, *, symbols: list[str], provider: EventProvider = yfinance_events
) -> Path:
    payload = build_event_layer(agent_root, run_date, symbols=symbols, provider=provider)
    out = default_event_path(agent_root, run_date)
    write_json(out, payload)
    return out
