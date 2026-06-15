from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_postmarket_archive_payload(run_date: str, summary: str) -> dict[str, object]:
    return {
        "date": run_date,
        "summary": summary,
    }


def _read_json_or(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            records.append(payload)
    return records


def _money(value: Any) -> float:
    return round(float(value or 0), 2)


def _field(payload: Any, key: str, default: Any = 0) -> Any:
    if not isinstance(payload, dict):
        return default
    return payload.get(key, default)


def build_paper_postmarket_summary(
    *,
    run_date: str,
    day_start_path: Path,
    day_end_path: Path,
    orders_log_path: Path,
    daily_usage_path: Path,
) -> dict[str, object]:
    day_start = _read_json_or(day_start_path, {})
    day_end = _read_json_or(day_end_path, {})
    orders = _read_jsonl(orders_log_path)
    daily_usage = _read_json_or(daily_usage_path, {})
    filled_orders = [order for order in orders if str(order.get("status", "")).lower() == "filled"]
    rejected_orders = [order for order in orders if str(order.get("status", "")).lower() in {"rejected", "canceled", "cancelled"}]
    starting_equity = _money(_field(day_start, "total_equity"))
    ending_equity = _money(_field(day_end, "total_equity"))
    starting_cash = _money(_field(day_start, "cash"))
    ending_cash = _money(_field(day_end, "cash"))
    positions = _field(day_end, "positions", {})
    if not isinstance(positions, dict):
        positions = {}
    return {
        "date": run_date,
        "trading_mode": "paper",
        "starting_cash": starting_cash,
        "ending_cash": ending_cash,
        "cash_change": _money(ending_cash - starting_cash),
        "starting_total_equity": starting_equity,
        "ending_total_equity": ending_equity,
        "total_equity_change": _money(ending_equity - starting_equity),
        "realized_pnl": _money(_field(day_end, "realized_pnl")),
        "positions_market_value": _money(_field(day_end, "positions_market_value")),
        "open_position_count": len(positions),
        "open_positions": sorted(positions),
        "order_count": len(orders),
        "filled_order_count": len(filled_orders),
        "rejected_or_canceled_order_count": len(rejected_orders),
        "filled_notional": _money(sum(float(order.get("notional", 0) or 0) for order in filled_orders)),
        "daily_usage": daily_usage if isinstance(daily_usage, dict) else {},
    }
