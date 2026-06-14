from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import ensure_dir, read_json, write_json
from trading_agent.core.time import PT
from trading_agent.policy.models import OrderIntent, PolicyDecision


@dataclass(frozen=True)
class PaperFillResult:
    applied: bool
    reason: str = ""


def _read_json_or(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return read_json(path)


def _initialize_account(path: Path, starting_cash: float) -> dict[str, Any]:
    account = _read_json_or(path, None)
    if isinstance(account, dict):
        return account
    return {
        "cash": round(float(starting_cash), 2),
        "starting_cash": round(float(starting_cash), 2),
        "realized_pnl": 0.0,
        "updated_at": datetime.now(tz=PT).isoformat(),
    }


def _append_order(path: Path, payload: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _position_payload(position: Any, symbol: str) -> dict[str, Any]:
    if isinstance(position, dict):
        payload = dict(position)
        payload.setdefault("symbol", symbol)
        return payload
    return {
        "symbol": getattr(position, "symbol", symbol),
        "quantity": getattr(position, "quantity", 0.0),
        "average_cost": getattr(position, "average_cost", 0.0),
        "market_price": getattr(position, "market_price", 0.0),
    }


def _normalize_positions(positions: Any) -> dict[str, Any]:
    if not isinstance(positions, dict):
        return {}
    return {str(symbol).upper(): _position_payload(position, str(symbol).upper()) for symbol, position in positions.items()}


def _positions_market_value(positions: dict[str, Any]) -> float:
    total = 0.0
    for position in positions.values():
        if not isinstance(position, dict):
            continue
        quantity = float(position.get("quantity", 0) or 0)
        price = float(position.get("market_price") or position.get("price") or position.get("last_trade_price") or 0)
        total += quantity * price
    return round(total, 2)


def _snapshot_payload(
    *,
    run_date: str,
    event: str,
    account: dict[str, Any],
    positions: dict[str, Any],
    timestamp: str | None = None,
) -> dict[str, Any]:
    resolved_timestamp = timestamp or datetime.now(tz=PT).isoformat()
    cash = round(float(account.get("cash", account.get("buying_power", 0)) or 0), 2)
    positions_value = _positions_market_value(positions)
    return {
        "timestamp": resolved_timestamp,
        "date": run_date,
        "event": event,
        "cash": cash,
        "starting_cash": round(float(account.get("starting_cash", cash) or cash), 2),
        "realized_pnl": round(float(account.get("realized_pnl", 0) or 0), 2),
        "positions_market_value": positions_value,
        "total_equity": round(cash + positions_value, 2),
        "positions": positions,
    }


def _append_equity_point(path: Path, payload: dict[str, Any]) -> None:
    point = {key: value for key, value in payload.items() if key != "positions"}
    _append_order(path, point)


def record_paper_day_start(
    agent_root: Path,
    *,
    run_date: str,
    starting_cash: float,
    positions: dict[str, Any] | None = None,
) -> bool:
    paths = build_runtime_paths(agent_root, run_date=run_date)
    if paths.paper_day_start_path.exists():
        return False
    account = _initialize_account(paths.paper_account_path, starting_cash)
    normalized_positions = _normalize_positions(positions) if positions is not None else _read_json_or(paths.paper_positions_path, {})
    if not isinstance(normalized_positions, dict):
        normalized_positions = {}
    payload = _snapshot_payload(run_date=run_date, event="day_start", account=account, positions=normalized_positions)
    write_json(paths.paper_account_path, account)
    write_json(paths.paper_positions_path, normalized_positions)
    write_json(paths.paper_day_start_path, payload)
    _append_equity_point(paths.paper_equity_curve_path, payload)
    return True


def record_paper_day_end(agent_root: Path, *, run_date: str) -> bool:
    paths = build_runtime_paths(agent_root, run_date=run_date)
    account = _initialize_account(paths.paper_account_path, 0.0)
    positions = _read_json_or(paths.paper_positions_path, {})
    if not isinstance(positions, dict):
        positions = {}
    payload = _snapshot_payload(run_date=run_date, event="day_end", account=account, positions=positions)
    write_json(paths.paper_day_end_path, payload)
    _append_equity_point(paths.paper_equity_curve_path, payload)
    return True


def _update_daily_usage(path: Path, *, run_date: str, notional: float, timestamp: str) -> None:
    usage = _read_json_or(path, {})
    if not isinstance(usage, dict):
        usage = {}
    usage.setdefault("date", run_date)
    usage["used_notional"] = round(float(usage.get("used_notional", 0) or 0) + notional, 2)
    usage["paper_filled_notional"] = round(float(usage.get("paper_filled_notional", 0) or 0) + notional, 2)
    usage["paper_order_count"] = int(usage.get("paper_order_count", 0) or 0) + 1
    usage["updated_at"] = timestamp
    write_json(path, usage)


def _apply_buy(account: dict[str, Any], positions: dict[str, Any], intent: OrderIntent) -> PaperFillResult:
    cash = float(account.get("cash", 0) or 0)
    notional = round(intent.quantity * intent.limit_price, 2)
    if notional > cash:
        return PaperFillResult(False, "insufficient_paper_cash")
    position = positions.get(intent.symbol, {})
    old_qty = float(position.get("quantity", 0) or 0)
    old_cost = float(position.get("average_cost", 0) or 0)
    new_qty = old_qty + intent.quantity
    new_average = ((old_qty * old_cost) + notional) / new_qty if new_qty else 0.0
    positions[intent.symbol] = {
        "symbol": intent.symbol,
        "quantity": round(new_qty, 8),
        "average_cost": round(new_average, 4),
        "market_price": intent.limit_price,
    }
    account["cash"] = round(cash - notional, 2)
    return PaperFillResult(True)


def _apply_sell(account: dict[str, Any], positions: dict[str, Any], intent: OrderIntent) -> PaperFillResult:
    position = positions.get(intent.symbol)
    if not position:
        return PaperFillResult(False, "missing_paper_position")
    old_qty = float(position.get("quantity", 0) or 0)
    if old_qty < intent.quantity:
        return PaperFillResult(False, "insufficient_paper_position")
    average_cost = float(position.get("average_cost", 0) or 0)
    proceeds = round(intent.quantity * intent.limit_price, 2)
    account["cash"] = round(float(account.get("cash", 0) or 0) + proceeds, 2)
    account["realized_pnl"] = round(float(account.get("realized_pnl", 0) or 0) + (intent.limit_price - average_cost) * intent.quantity, 2)
    new_qty = old_qty - intent.quantity
    if new_qty <= 0:
        positions.pop(intent.symbol, None)
    else:
        position["quantity"] = round(new_qty, 8)
        position["market_price"] = intent.limit_price
    return PaperFillResult(True)


def apply_paper_intent(
    agent_root: Path,
    *,
    run_date: str,
    decision: PolicyDecision,
    starting_cash: float,
) -> PaperFillResult:
    if decision.trading_mode != "paper" or decision.decision != "would_trade" or decision.intent is None:
        return PaperFillResult(False, "no_paper_fill")

    paths = build_runtime_paths(agent_root, run_date=run_date)
    record_paper_day_start(agent_root, run_date=run_date, starting_cash=starting_cash)
    account = _initialize_account(paths.paper_account_path, starting_cash)
    positions = _read_json_or(paths.paper_positions_path, {})
    if not isinstance(positions, dict):
        positions = {}

    intent = decision.intent
    result = _apply_buy(account, positions, intent) if intent.side == "buy" else _apply_sell(account, positions, intent)
    if not result.applied:
        return result

    now = datetime.now(tz=PT).isoformat()
    account["updated_at"] = now
    order = {
        "timestamp": now,
        "symbol": intent.symbol,
        "side": intent.side,
        "quantity": intent.quantity,
        "limit_price": intent.limit_price,
        "notional": round(intent.quantity * intent.limit_price, 2),
        "status": "filled",
        "reason_codes": list(intent.reason_codes),
        "confidence": intent.confidence,
    }
    write_json(paths.paper_account_path, account)
    write_json(paths.paper_positions_path, positions)
    _append_order(paths.paper_orders_log_path, order)
    _update_daily_usage(paths.daily_usage_path, run_date=run_date, notional=order["notional"], timestamp=now)
    _append_equity_point(
        paths.paper_equity_curve_path,
        _snapshot_payload(run_date=run_date, event="fill", account=account, positions=positions, timestamp=now),
    )
    return result
