from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from trading_agent.data.universe import parse_universe
from trading_agent.policy.models import OpenOrder, PolicyInputs, Position, Quote


class RobinhoodPolicyGateway(Protocol):
    def get_account(self) -> dict[str, Any]:
        """Return sanitized account-level values for the dedicated Agentic account."""

    def list_positions(self) -> list[dict[str, Any]]:
        """Return equity positions for the dedicated Agentic account."""

    def list_open_orders(self) -> list[dict[str, Any]]:
        """Return currently open equity orders for the dedicated Agentic account."""

    def get_quotes(self, symbols: list[str]) -> list[dict[str, Any]]:
        """Return current equity quotes for the requested symbols."""


def _read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_allowlist(path: Path) -> list[str]:
    if not path.exists():
        return []
    symbols: list[str] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        candidate = line.split("#", 1)[0].strip().upper()
        if candidate and candidate not in seen:
            symbols.append(candidate)
            seen.add(candidate)
    return symbols


def _load_research_reports(root: Path, run_date: str) -> dict[str, dict[str, Any]]:
    report_dir = root / "state" / "research_reports" / run_date
    if not report_dir.exists():
        return {}
    reports: dict[str, dict[str, Any]] = {}
    for path in sorted(report_dir.glob("*.json")):
        payload = _read_json_if_exists(path)
        symbol = str(payload.get("symbol") or path.stem).upper()
        reports[symbol] = payload
    return reports


def _as_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _symbol(payload: dict[str, Any]) -> str:
    return str(payload.get("symbol") or payload.get("ticker") or "").upper()


def _sanitize_account(payload: dict[str, Any]) -> dict[str, Any]:
    account: dict[str, Any] = {}
    if "buying_power" in payload:
        account["buying_power"] = _as_float(payload.get("buying_power"))
    elif "cash_available_for_trading" in payload:
        account["buying_power"] = _as_float(payload.get("cash_available_for_trading"))
    if "account_type" in payload:
        account["account_type"] = str(payload["account_type"])
    if "status" in payload:
        account["status"] = str(payload["status"])
    return account


def _parse_position(payload: dict[str, Any]) -> Position | None:
    symbol = _symbol(payload)
    quantity = _as_float(payload.get("quantity"))
    if not symbol or quantity <= 0:
        return None
    return Position(
        symbol=symbol,
        quantity=quantity,
        average_cost=_as_float(payload.get("average_cost") or payload.get("average_buy_price")),
        market_price=_as_float(payload.get("market_price") or payload.get("price") or payload.get("last_trade_price")),
    )


def _parse_open_order(payload: dict[str, Any]) -> OpenOrder | None:
    symbol = _symbol(payload)
    side = str(payload.get("side") or "").lower()
    if not symbol or side not in {"buy", "sell"}:
        return None
    return OpenOrder(
        symbol=symbol,
        side=side,
        quantity=_as_float(payload.get("quantity") or payload.get("cumulative_quantity")),
        notional=_as_float(payload.get("notional") or payload.get("estimated_notional")),
        status=str(payload.get("status") or "open"),
    )


def _parse_quote(payload: dict[str, Any]) -> Quote | None:
    symbol = _symbol(payload)
    price = _as_float(
        payload.get("price")
        or payload.get("last_trade_price")
        or payload.get("last_price")
        or payload.get("mark_price")
    )
    if not symbol or price <= 0:
        return None
    previous_close = payload.get("previous_close") or payload.get("previous_close_price")
    return Quote(
        symbol=symbol,
        price=price,
        previous_close=_as_float(previous_close, default=0.0) if previous_close is not None else None,
        timestamp=str(payload.get("timestamp") or payload.get("updated_at") or ""),
        is_fresh=bool(payload.get("is_fresh", True)),
    )


def _quote_symbols(inputs: PolicyInputs) -> list[str]:
    symbols: list[str] = []
    candidates: list[str] = []
    if inputs.daily_plan and isinstance(inputs.daily_plan.get("today_watchlist"), list):
        candidates.extend(str(symbol) for symbol in inputs.daily_plan["today_watchlist"])
    candidates.extend(inputs.today_allowlist)
    candidates.extend(inputs.universe)
    candidates.extend(inputs.positions)
    for order in inputs.open_orders:
        candidates.append(order.symbol)
    for candidate in candidates:
        symbol = str(candidate).upper()
        if symbol and symbol not in symbols:
            symbols.append(symbol)
    return symbols


def _hydrate_robinhood_inputs(inputs: PolicyInputs, gateway: RobinhoodPolicyGateway | None) -> None:
    if gateway is None:
        return
    try:
        inputs.account = _sanitize_account(gateway.get_account())
        inputs.positions = {
            position.symbol: position
            for payload in gateway.list_positions()
            if (position := _parse_position(payload)) is not None
        }
        inputs.open_orders = [
            order
            for payload in gateway.list_open_orders()
            if (order := _parse_open_order(payload)) is not None
        ]
        inputs.quotes = {
            quote.symbol: quote
            for payload in gateway.get_quotes(_quote_symbols(inputs))
            if (quote := _parse_quote(payload)) is not None
        }
    except Exception:
        inputs.account = {}
        inputs.positions = {}
        inputs.open_orders = []
        inputs.quotes = {}


def load_policy_inputs(
    agent_root: Path,
    *,
    run_date: str,
    trading_mode: str,
    risk_tier: int,
    robinhood_gateway: RobinhoodPolicyGateway | None = None,
) -> PolicyInputs:
    config_dir = agent_root / "config"
    state_dir = agent_root / "state"
    risk_tiers = _read_json_if_exists(config_dir / "risk_tiers.json")
    risk_caps = risk_tiers.get(str(risk_tier), {}) if isinstance(risk_tiers, dict) else {}
    daily_plan = _read_json_if_exists(state_dir / "daily_plan.json") or None

    inputs = PolicyInputs(
        run_date=run_date,
        trading_mode=trading_mode,
        risk_tier=risk_tier,
        risk_caps=risk_caps,
        universe=parse_universe(config_dir / "universe.txt") if (config_dir / "universe.txt").exists() else [],
        today_allowlist=_read_allowlist(state_dir / "today_allowlist.txt"),
        daily_plan=daily_plan,
        dynamic_allowlist=_read_json_if_exists(state_dir / "dynamic_allowlist.json"),
        daily_usage=_read_json_if_exists(state_dir / "daily_usage.json"),
        dsa_signals=_read_json_if_exists(state_dir / "dsa_signals.json"),
        kronos_signals=_read_json_if_exists(state_dir / "kronos_signals.json"),
        technical_signals=_read_json_if_exists(state_dir / "technical_signals.json"),
        research_reports=_load_research_reports(agent_root, run_date),
        kill_switch_present=(agent_root / "KILL_SWITCH").exists(),
    )
    _hydrate_robinhood_inputs(inputs, robinhood_gateway)
    return inputs
