from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Protocol

from trading_agent.core.context import build_runtime_paths
from trading_agent.paper.broker import pending_paper_orders
from trading_agent.data.universe import parse_universe
from trading_agent.policy.models import OpenOrder, PolicyInputs, Position, Quote
from trading_agent.policy.profiles import load_policy_profile
from trading_agent.portfolio.target import load_theme_map
from trading_agent.signals.technical_fallback import merge_technical_signals


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


def _dated_payload_is_fresh(payload: dict[str, Any], run_date: str) -> bool:
    for key in ("date", "as_of"):
        value = payload.get(key)
        if value is None:
            continue
        return str(value) == run_date
    return True


def _read_json_if_fresh(path: Path, run_date: str) -> dict[str, Any]:
    payload = _read_json_if_exists(path)
    if not payload:
        return {}
    return payload if _dated_payload_is_fresh(payload, run_date) else {}


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
    report_dir = build_runtime_paths(root, run_date=run_date).run_state_dir / "research_reports"
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
    raw_bid = payload.get("bid")
    raw_ask = payload.get("ask")
    bid = _as_float(raw_bid) if raw_bid not in (None, "") else None
    ask = _as_float(raw_ask) if raw_ask not in (None, "") else None
    return Quote(
        symbol=symbol,
        price=price,
        previous_close=_as_float(previous_close, default=0.0) if previous_close is not None else None,
        timestamp=str(payload.get("timestamp") or payload.get("updated_at") or ""),
        is_fresh=bool(payload.get("is_fresh", True)),
        bid=bid if bid and bid > 0 else None,
        ask=ask if ask and ask > 0 else None,
    )


def _payload_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        rows: list[dict[str, Any]] = []
        for key, item in value.items():
            if not isinstance(item, dict):
                continue
            payload = dict(item)
            payload.setdefault("symbol", key)
            rows.append(payload)
        return rows
    return []


def _hydrate_account_snapshot(inputs: PolicyInputs, snapshot: dict[str, Any]) -> None:
    account_payload = {
        "buying_power": snapshot.get("buying_power"),
        "account_type": "agentic" if snapshot.get("agentic_account_identified") else snapshot.get("account_type"),
        "status": snapshot.get("data_status"),
    }
    if isinstance(snapshot.get("account"), dict):
        account_payload.update(snapshot["account"])
    inputs.account = _sanitize_account(account_payload)
    inputs.positions = {
        position.symbol: position
        for payload in _payload_list(snapshot.get("current_positions") or snapshot.get("positions") or snapshot.get("equity_positions"))
        if (position := _parse_position(payload)) is not None
    }
    inputs.open_orders = [
        order
        for payload in _payload_list(snapshot.get("open_orders") or snapshot.get("equity_orders") or snapshot.get("orders"))
        if (order := _parse_open_order(payload)) is not None and order.status.lower() in {"open", "queued", "new", "pending", "partially_filled"}
    ]


def _hydrate_quote_snapshot(inputs: PolicyInputs, snapshot: dict[str, Any]) -> None:
    candidates = snapshot.get("quotes") or snapshot.get("equity_quotes") or snapshot.get("symbols")
    for payload in _payload_list(candidates):
        quote = _parse_quote(payload)
        if quote is not None:
            inputs.quotes[quote.symbol] = quote


def _quote_symbols(inputs: PolicyInputs) -> list[str]:
    symbols: list[str] = []
    candidates: list[str] = []
    if inputs.daily_plan and isinstance(inputs.daily_plan.get("today_watchlist"), list):
        candidates.extend(str(symbol) for symbol in inputs.daily_plan["today_watchlist"])
    candidates.extend(inputs.today_allowlist)
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


def _hydrate_snapshots_if_present(inputs: PolicyInputs, paths: Any) -> None:
    account = _read_json_if_exists(paths.account_snapshot_path)
    if account:
        _hydrate_account_snapshot(inputs, account)
    for quote_path in (paths.quote_snapshot_core_path, paths.quote_snapshot_candidates_path):
        quote_snapshot = _read_json_if_exists(quote_path)
        if quote_snapshot:
            _hydrate_quote_snapshot(inputs, quote_snapshot)


def _hydrate_live_quotes(
    inputs: PolicyInputs,
    quote_provider: Callable[[list[str]], list[dict[str, Any]]] | None,
    *,
    require_live_quotes: bool,
) -> None:
    if quote_provider is None:
        return
    symbols = _quote_symbols(inputs)
    try:
        payloads = quote_provider(symbols)
    except Exception:
        payloads = []
    live_quotes = {
        quote.symbol: quote
        for payload in payloads
        if (quote := _parse_quote(payload)) is not None
    }
    if require_live_quotes:
        inputs.quotes = live_quotes
        return
    inputs.quotes.update(live_quotes)


def _hydrate_advisory_overlay_if_enabled(inputs: PolicyInputs, paths: Any) -> None:
    if os.environ.get("ENABLE_INTRADAY_ADVISORY_OVERLAY", "0") != "1":
        return
    from trading_agent.policy.advisory_overlay import build_advisory_overlay, load_advisory_artifacts

    artifacts = load_advisory_artifacts(paths)
    inputs.advisory_overlay = build_advisory_overlay(inputs, artifacts)


def _hydrate_paper_ledger_if_present(inputs: PolicyInputs, paths: Any) -> None:
    if inputs.trading_mode != "paper":
        return
    account = _read_json_if_exists(paths.paper_account_path)
    if account:
        inputs.account = {"buying_power": _as_float(account.get("cash"))}
        if "starting_cash" in account:
            inputs.account["starting_cash"] = _as_float(account.get("starting_cash"))
        if "realized_pnl" in account:
            inputs.account["realized_pnl"] = _as_float(account.get("realized_pnl"))
    positions_payload = _read_json_if_exists(paths.paper_positions_path)
    if positions_payload:
        inputs.positions = {
            position.symbol: position
            for payload in _payload_list(positions_payload)
            if (position := _parse_position(payload)) is not None
        }
    pending_orders = [
        order
        for payload in pending_paper_orders(paths.agent_root, run_date=paths.run_date, paths_override=paths)
        if (order := _parse_open_order(payload)) is not None
    ]
    existing = {(order.symbol, order.side, order.quantity, order.status): order for order in inputs.open_orders}
    for order in pending_orders:
        existing.setdefault((order.symbol, order.side, order.quantity, order.status), order)
    inputs.open_orders = list(existing.values())


def hydrate_paper_ledger(inputs: PolicyInputs, paths: Any) -> None:
    """Public: overlay account/positions/pending-orders from the paper ledger rooted at `paths`.
    Used by the shadow runner to hydrate a challenger from its own isolated experiment ledger (G9)."""
    _hydrate_paper_ledger_if_present(inputs, paths)


def load_policy_inputs(
    agent_root: Path,
    *,
    run_date: str,
    trading_mode: str,
    risk_tier: int,
    robinhood_gateway: RobinhoodPolicyGateway | None = None,
    quote_provider: Callable[[list[str]], list[dict[str, Any]]] | None = None,
    require_live_quotes: bool = False,
    policy_profile_name: str | None = None,
) -> PolicyInputs:
    paths = build_runtime_paths(agent_root, run_date=run_date)
    config_dir = paths.config_dir
    risk_tiers = _read_json_if_exists(config_dir / "risk_tiers.json")
    risk_caps = risk_tiers.get(str(risk_tier), {}) if isinstance(risk_tiers, dict) else {}
    daily_plan = _read_json_if_fresh(paths.daily_plan_path, run_date) or None

    inputs = PolicyInputs(
        run_date=run_date,
        trading_mode=trading_mode,
        risk_tier=risk_tier,
        risk_caps=risk_caps,
        universe=parse_universe(config_dir / "universe.txt") if (config_dir / "universe.txt").exists() else [],
        today_allowlist=_read_allowlist(paths.today_allowlist_path),
        daily_plan=daily_plan,
        dynamic_allowlist=_read_json_if_fresh(paths.dynamic_allowlist_path, run_date),
        candidate_scores=_read_json_if_fresh(paths.candidate_scores_path, run_date),
        risk_overlay=_read_json_if_fresh(paths.risk_overlay_path, run_date),
        trader_watch_levels=_read_json_if_exists(paths.trader_watch_levels_path),
        data_status_summary=_read_json_if_fresh(paths.data_status_summary_path, run_date),
        capital_snapshot=_read_json_if_fresh(paths.capital_snapshot_path, run_date),
        catalyst_snapshot=_read_json_if_fresh(paths.catalyst_snapshot_path, run_date),
        policy_profile=load_policy_profile(agent_root, profile_name=policy_profile_name),
        daily_usage=_read_json_if_fresh(paths.daily_usage_path, run_date),
        dsa_signals=_read_json_if_fresh(paths.dsa_signals_path, run_date),
        kronos_signals=_read_json_if_fresh(paths.kronos_signals_path, run_date),
        technical_signals=merge_technical_signals(
            _read_json_if_fresh(paths.technical_signals_full_path, run_date),
            _read_json_if_fresh(paths.technical_signals_path, run_date),
        ),
        research_reports=_load_research_reports(agent_root, run_date),
        kill_switch_present=(agent_root / "KILL_SWITCH").exists(),
        theme_map=load_theme_map(config_dir),
        deterministic_execution=os.environ.get("ENABLE_DETERMINISTIC_INTRADAY", "0") == "1",
    )
    if robinhood_gateway is None:
        _hydrate_snapshots_if_present(inputs, paths)
    else:
        _hydrate_robinhood_inputs(inputs, robinhood_gateway)
    _hydrate_paper_ledger_if_present(inputs, paths)
    _hydrate_live_quotes(inputs, quote_provider, require_live_quotes=require_live_quotes)
    _hydrate_advisory_overlay_if_enabled(inputs, paths)
    if not inputs.today_allowlist and inputs.risk_overlay:
        tradable = [str(s).upper() for s in (inputs.risk_overlay.get("tradable_candidates") or []) if s]
        if tradable:
            inputs.today_allowlist = tradable
    return inputs
