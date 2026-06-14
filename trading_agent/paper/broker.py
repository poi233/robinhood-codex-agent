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
    return result
