from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import ensure_dir, read_json, write_json
from trading_agent.core.time import PT
from trading_agent.policy.models import OrderIntent, PolicyDecision, Quote


@dataclass(frozen=True)
class PaperFillResult:
    applied: bool
    status: str = "rejected"
    reason: str = ""


def _read_json_or(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return read_json(path)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


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
    if str(os.environ.get("PAPER_CANCEL_PENDING_AT_DAY_END", "1") or "1") == "1":
        pending = pending_paper_orders(agent_root, run_date=run_date)
        if pending:
            now = datetime.now(tz=PT).isoformat()
            for order in pending:
                cancel_event = {
                    "order_id": order.get("order_id"),
                    "timestamp": now,
                    "event": "day_end_cancel",
                    "symbol": order.get("symbol"),
                    "side": order.get("side"),
                    "quantity": order.get("quantity"),
                    "limit_price": order.get("limit_price"),
                    "status": "pending_canceled",
                    "reason": "day_end_expired",
                }
                _append_order_event(paths.paper_orders_log_path, cancel_event)
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
    usage = _apply_usage_fill(usage, run_date=run_date, notional=notional, timestamp=timestamp)
    write_json(path, usage)


def _apply_usage_fill(usage: dict[str, Any], *, run_date: str, notional: float, timestamp: str) -> dict[str, Any]:
    usage.setdefault("date", run_date)
    usage["used_notional"] = round(float(usage.get("used_notional", 0) or 0) + notional, 2)
    usage["paper_filled_notional"] = round(float(usage.get("paper_filled_notional", 0) or 0) + notional, 2)
    usage["paper_order_count"] = int(usage.get("paper_order_count", 0) or 0) + 1
    usage["updated_at"] = timestamp
    return usage


def _reset_usage_counters_for_run_date(usage: dict[str, Any], *, run_date: str) -> dict[str, Any]:
    prior_date = str(usage.get("date") or "")
    if prior_date == run_date:
        return usage
    refreshed = dict(usage)
    refreshed["date"] = run_date
    refreshed["used_notional"] = 0.0
    refreshed["paper_filled_notional"] = 0.0
    refreshed["paper_order_count"] = 0
    refreshed["new_positions_today"] = 0
    refreshed["new_position_symbols_today"] = []
    try:
        run_week = datetime.fromisoformat(run_date).isocalendar()[:2]
        prior_week = datetime.fromisoformat(prior_date).isocalendar()[:2] if prior_date else None
    except ValueError:
        run_week = None
        prior_week = None
    if run_week is None or prior_week != run_week:
        refreshed["new_positions_this_week"] = 0
    return refreshed


def _fill_model() -> str:
    return str(os.environ.get("PAPER_FILL_MODEL", "conservative") or "conservative").lower()


def _slippage_factor() -> float:
    bps = float(os.environ.get("PAPER_SLIPPAGE_BPS", "10") or "10")
    return bps / 10000.0


def _compute_fill_price(side: str, limit_price: float, reference_price: float, slippage: float) -> float:
    """Return realistic fill price given conservative model already cleared.

    Buy: pay at most limit; real fill is near reference (market) plus slippage.
    Sell: receive at least limit; real fill is near reference minus slippage.
    """
    if side == "buy":
        return round(min(limit_price, reference_price * (1.0 + slippage)), 4)
    return round(max(limit_price, reference_price * (1.0 - slippage)), 4)


def _partial_fill_enabled() -> bool:
    return str(os.environ.get("PAPER_PARTIAL_FILL", "0") or "0") == "1"


def _partial_fill_min_ratio() -> float:
    return float(os.environ.get("PAPER_PARTIAL_FILL_MIN_RATIO", "0.3") or "0.3")


def _partial_fill_threshold_bps() -> float:
    return float(os.environ.get("PAPER_PARTIAL_FILL_THRESHOLD_BPS", "20") or "20")


def _partial_fill_ratio(side: str, limit_price: float, reference_price: float) -> float:
    """Deterministic fill ratio for a quote that has just barely cleared the
    limit vs. one that has moved solidly through it (`_can_fill` already
    confirmed the limit is cleared before this runs).

    A quote sitting right at the limit fills at PAPER_PARTIAL_FILL_MIN_RATIO;
    a quote PAPER_PARTIAL_FILL_THRESHOLD_BPS or more through the limit fills
    in full. Linear in between. Deterministic (not random) so partial-fill
    tests are reproducible.
    """
    if limit_price <= 0:
        return 1.0
    if side == "buy":
        progress = (limit_price - reference_price) / limit_price
    else:
        progress = (reference_price - limit_price) / limit_price
    threshold = _partial_fill_threshold_bps() / 10000.0
    if threshold <= 0 or progress >= threshold:
        return 1.0
    min_ratio = _partial_fill_min_ratio()
    if progress <= 0:
        return min_ratio
    return min_ratio + (1.0 - min_ratio) * (progress / threshold)


def _resolve_fill_quantity(intent: OrderIntent) -> tuple[float, float]:
    """Return (filled_qty, remaining_qty) for this fill attempt.

    remaining_qty > 0 means the order is only partially filled and the
    remainder should be re-queued as a pending order for a later reconcile
    pass to pick up.
    """
    if not _partial_fill_enabled():
        return intent.quantity, 0.0
    reference_price = intent.reference_price if intent.reference_price is not None else intent.limit_price
    ratio = _partial_fill_ratio(intent.side, intent.limit_price, reference_price)
    if ratio >= 1.0:
        return intent.quantity, 0.0
    filled_qty = round(intent.quantity * ratio, 8)
    remaining_qty = round(intent.quantity - filled_qty, 8)
    if filled_qty <= 0 or remaining_qty <= 0:
        return intent.quantity, 0.0
    return filled_qty, remaining_qty


def _order_payload(intent: OrderIntent, *, now: str, status: str, unfilled_reason: str = "", fill_price: float | None = None) -> dict[str, Any]:
    return {
        "order_id": f"paper-{intent.symbol.lower()}-{int(datetime.now(tz=PT).timestamp() * 1000)}",
        "timestamp": now,
        "symbol": intent.symbol,
        "side": intent.side,
        "quantity": intent.quantity,
        "limit_price": intent.limit_price,
        "current_price_at_submit": intent.reference_price,
        "notional": round(intent.quantity * intent.limit_price, 2),
        "status": status,
        "filled_at": now if status == "filled" else None,
        "fill_price": fill_price if status == "filled" else None,
        "unfilled_reason": unfilled_reason or None,
        "reason_codes": list(intent.reason_codes),
        "confidence": intent.confidence,
    }


def _append_order_event(path: Path, payload: dict[str, Any]) -> None:
    _append_order(path, payload)


def _can_fill(intent: OrderIntent) -> tuple[bool, str]:
    model = _fill_model()
    if model == "immediate":
        return True, ""
    reference_price = intent.reference_price if intent.reference_price is not None else intent.limit_price
    if model == "conservative":
        if intent.side == "buy" and reference_price > intent.limit_price:
            return False, "buy_limit_not_reached"
        if intent.side == "sell" and reference_price < intent.limit_price:
            return False, "sell_limit_not_reached"
        return True, ""
    return False, "fill_model_not_supported"


def _apply_buy(account: dict[str, Any], positions: dict[str, Any], intent: OrderIntent, fill_price: float | None = None) -> PaperFillResult:
    actual_price = fill_price if fill_price is not None else intent.limit_price
    cash = float(account.get("cash", 0) or 0)
    notional = round(intent.quantity * actual_price, 2)
    if notional > cash:
        return PaperFillResult(False, "rejected", "insufficient_paper_cash")
    position = positions.get(intent.symbol, {})
    old_qty = float(position.get("quantity", 0) or 0)
    old_cost = float(position.get("average_cost", 0) or 0)
    new_qty = old_qty + intent.quantity
    new_average = ((old_qty * old_cost) + notional) / new_qty if new_qty else 0.0
    positions[intent.symbol] = {
        "symbol": intent.symbol,
        "quantity": round(new_qty, 8),
        "average_cost": round(new_average, 4),
        "market_price": actual_price,
    }
    account["cash"] = round(cash - notional, 2)
    return PaperFillResult(True, "filled")


def _apply_sell(account: dict[str, Any], positions: dict[str, Any], intent: OrderIntent, fill_price: float | None = None) -> PaperFillResult:
    actual_price = fill_price if fill_price is not None else intent.limit_price
    position = positions.get(intent.symbol)
    if not position:
        return PaperFillResult(False, "rejected", "missing_paper_position")
    old_qty = float(position.get("quantity", 0) or 0)
    if old_qty < intent.quantity:
        return PaperFillResult(False, "rejected", "insufficient_paper_position")
    average_cost = float(position.get("average_cost", 0) or 0)
    proceeds = round(intent.quantity * actual_price, 2)
    account["cash"] = round(float(account.get("cash", 0) or 0) + proceeds, 2)
    account["realized_pnl"] = round(float(account.get("realized_pnl", 0) or 0) + (actual_price - average_cost) * intent.quantity, 2)
    new_qty = old_qty - intent.quantity
    if new_qty <= 0:
        positions.pop(intent.symbol, None)
    else:
        position["quantity"] = round(new_qty, 8)
        position["market_price"] = actual_price
    return PaperFillResult(True, "filled")


def _update_trade_counters(usage: dict[str, Any], *, run_date: str, intent: OrderIntent) -> None:
    if intent.side == "buy":
        by_symbol = usage.setdefault("last_buy_date_by_symbol", {})
        if isinstance(by_symbol, dict):
            new_position_symbols = usage.setdefault("new_position_symbols_today", [])
            if isinstance(new_position_symbols, list) and intent.symbol not in new_position_symbols:
                new_position_symbols.append(intent.symbol)
                usage["new_positions_today"] = int(usage.get("new_positions_today", 0) or 0) + 1
                usage["new_positions_this_week"] = int(usage.get("new_positions_this_week", 0) or 0) + 1
            by_symbol[intent.symbol] = run_date
    if intent.side == "sell":
        by_symbol = usage.setdefault("last_sell_date_by_symbol", {})
        if isinstance(by_symbol, dict):
            by_symbol[intent.symbol] = run_date
        if {"risk_exit", "full_invalidation_exit"} & set(intent.reason_codes):
            stop_dates = usage.setdefault("last_stop_date_by_symbol", {})
            if isinstance(stop_dates, dict):
                stop_dates[intent.symbol] = run_date


def apply_paper_intent(
    agent_root: Path,
    *,
    run_date: str,
    decision: PolicyDecision,
    starting_cash: float,
) -> PaperFillResult:
    if decision.trading_mode != "paper" or decision.decision != "would_trade" or decision.intent is None:
        return PaperFillResult(False, "rejected", "no_paper_fill")

    paths = build_runtime_paths(agent_root, run_date=run_date)
    record_paper_day_start(agent_root, run_date=run_date, starting_cash=starting_cash)
    account = _initialize_account(paths.paper_account_path, starting_cash)
    positions = _read_json_or(paths.paper_positions_path, {})
    if not isinstance(positions, dict):
        positions = {}
    usage = _read_json_or(paths.daily_usage_path, {})
    if not isinstance(usage, dict):
        usage = {}
    usage = _reset_usage_counters_for_run_date(usage, run_date=run_date)
    write_json(paths.daily_usage_path, usage)

    intent = decision.intent
    can_fill, pending_reason = _can_fill(intent)
    now = datetime.now(tz=PT).isoformat()
    if not can_fill:
        _append_order(paths.paper_orders_log_path, _order_payload(intent, now=now, status="pending", unfilled_reason=pending_reason))
        return PaperFillResult(False, "pending", pending_reason)
    slippage = _slippage_factor()
    fill_price = _compute_fill_price(intent.side, intent.limit_price, intent.reference_price or intent.limit_price, slippage)
    filled_qty, remaining_qty = _resolve_fill_quantity(intent)
    fill_intent = intent if remaining_qty <= 0 else replace(intent, quantity=filled_qty)
    result = (
        _apply_buy(account, positions, fill_intent, fill_price=fill_price)
        if intent.side == "buy"
        else _apply_sell(account, positions, fill_intent, fill_price=fill_price)
    )
    if not result.applied:
        return result

    account["updated_at"] = now
    status = "partial_filled" if remaining_qty > 0 else "filled"
    order = _order_payload(fill_intent, now=now, status=status, fill_price=fill_price)
    order["filled_qty"] = filled_qty
    order["remaining_qty"] = remaining_qty
    order["original_quantity"] = intent.quantity
    write_json(paths.paper_account_path, account)
    write_json(paths.paper_positions_path, positions)
    _append_order(paths.paper_orders_log_path, order)
    usage = _read_json_or(paths.daily_usage_path, {})
    if not isinstance(usage, dict):
        usage = {}
    _update_trade_counters(usage, run_date=run_date, intent=fill_intent)
    write_json(paths.daily_usage_path, usage)
    _update_daily_usage(paths.daily_usage_path, run_date=run_date, notional=order["notional"], timestamp=now)
    _append_equity_point(
        paths.paper_equity_curve_path,
        _snapshot_payload(run_date=run_date, event="fill", account=account, positions=positions, timestamp=now),
    )
    if remaining_qty > 0:
        _append_order_event(
            paths.paper_orders_log_path,
            {
                "order_id": order["order_id"],
                "timestamp": now,
                "event": "partial_remainder_pending",
                "symbol": intent.symbol,
                "side": intent.side,
                "quantity": remaining_qty,
                "limit_price": intent.limit_price,
                "status": "pending",
                "reason_codes": list(intent.reason_codes),
                "confidence": intent.confidence,
            },
        )
    return result


def pending_paper_orders(agent_root: Path, *, run_date: str) -> list[dict[str, Any]]:
    paths = build_runtime_paths(agent_root, run_date=run_date)
    rows = _read_jsonl(paths.paper_orders_log_path)
    latest_by_order_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        order_id = str(row.get("order_id") or "")
        if not order_id:
            continue
        latest_by_order_id[order_id] = row
    return [
        row
        for row in latest_by_order_id.values()
        if str(row.get("status") or "").lower() in {"pending", "open", "queued"}
    ]


def _rebuild_intent_from_order(order: dict[str, Any]) -> OrderIntent | None:
    try:
        symbol = str(order["symbol"]).upper()
        side = str(order["side"]).lower()
        limit_price = float(order["limit_price"])
        quantity = float(order["quantity"])
    except (KeyError, TypeError, ValueError):
        return None
    if side not in {"buy", "sell"} or quantity <= 0 or limit_price <= 0:
        return None
    return OrderIntent(
        symbol=symbol,
        side=side,
        order_type="limit",
        limit_price=limit_price,
        estimated_notional=round(limit_price * quantity, 2),
        quantity=quantity,
        reference_price=float(order.get("current_price_at_submit") or limit_price),
        reason_codes=list(order.get("reason_codes") or []),
        confidence=float(order.get("confidence") or 0.0),
    )


def reconcile_pending_paper_orders(
    agent_root: Path,
    *,
    run_date: str,
    quotes: dict[str, Quote],
    starting_cash: float,
) -> list[dict[str, Any]]:
    paths = build_runtime_paths(agent_root, run_date=run_date)
    pending_orders = pending_paper_orders(agent_root, run_date=run_date)
    if not pending_orders:
        return []
    account = _initialize_account(paths.paper_account_path, starting_cash)
    positions = _read_json_or(paths.paper_positions_path, {})
    if not isinstance(positions, dict):
        positions = {}
    events: list[dict[str, Any]] = []
    usage = _read_json_or(paths.daily_usage_path, {})
    if not isinstance(usage, dict):
        usage = {}
    usage = _reset_usage_counters_for_run_date(usage, run_date=run_date)

    for order in pending_orders:
        intent = _rebuild_intent_from_order(order)
        if intent is None:
            continue
        quote = quotes.get(intent.symbol)
        if quote is None or quote.price <= 0:
            continue
        refreshed_intent = OrderIntent(
            symbol=intent.symbol,
            side=intent.side,
            order_type=intent.order_type,
            limit_price=intent.limit_price,
            estimated_notional=intent.estimated_notional,
            quantity=intent.quantity,
            reference_price=quote.price,
            reason_codes=list(intent.reason_codes),
            confidence=intent.confidence,
        )
        can_fill, _ = _can_fill(refreshed_intent)
        if not can_fill:
            continue
        slippage = _slippage_factor()
        fill_price = _compute_fill_price(refreshed_intent.side, refreshed_intent.limit_price, refreshed_intent.reference_price or refreshed_intent.limit_price, slippage)
        filled_qty, remaining_qty = _resolve_fill_quantity(refreshed_intent)
        fill_intent = refreshed_intent if remaining_qty <= 0 else replace(refreshed_intent, quantity=filled_qty)
        result = (
            _apply_buy(account, positions, fill_intent, fill_price=fill_price)
            if fill_intent.side == "buy"
            else _apply_sell(account, positions, fill_intent, fill_price=fill_price)
        )
        if not result.applied:
            continue
        now = datetime.now(tz=PT).isoformat()
        fill_event = {
            "order_id": order.get("order_id"),
            "timestamp": now,
            "event": "pending_filled",
            "symbol": fill_intent.symbol,
            "side": fill_intent.side,
            "quantity": fill_intent.quantity,
            "limit_price": fill_intent.limit_price,
            "fill_price": fill_price,
            "status": "partial_filled" if remaining_qty > 0 else "filled",
            "filled_qty": filled_qty,
            "remaining_qty": remaining_qty,
            "reason_codes": list(fill_intent.reason_codes),
        }
        _append_order_event(paths.paper_orders_log_path, fill_event)
        _update_trade_counters(usage, run_date=run_date, intent=fill_intent)
        usage = _apply_usage_fill(
            usage,
            run_date=run_date,
            notional=round(fill_intent.quantity * fill_price, 2),
            timestamp=now,
        )
        events.append(fill_event)
        if remaining_qty > 0:
            _append_order_event(
                paths.paper_orders_log_path,
                {
                    "order_id": order.get("order_id"),
                    "timestamp": now,
                    "event": "partial_remainder_pending",
                    "symbol": refreshed_intent.symbol,
                    "side": refreshed_intent.side,
                    "quantity": remaining_qty,
                    "limit_price": refreshed_intent.limit_price,
                    "status": "pending",
                    "reason_codes": list(refreshed_intent.reason_codes),
                    "confidence": refreshed_intent.confidence,
                },
            )

    if events:
        write_json(paths.paper_account_path, account)
        write_json(paths.paper_positions_path, positions)
        write_json(paths.daily_usage_path, usage)
        _append_equity_point(
            paths.paper_equity_curve_path,
            _snapshot_payload(run_date=run_date, event="pending_fill", account=account, positions=positions),
        )
    return events
