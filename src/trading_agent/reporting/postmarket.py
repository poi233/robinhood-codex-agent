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


def _latest_jsonl(path: Path) -> dict[str, Any]:
    rows = _read_jsonl(path)
    return rows[-1] if rows else {}


def _money(value: Any) -> float:
    return round(float(value or 0), 2)


def _field(payload: Any, key: str, default: Any = 0) -> Any:
    if not isinstance(payload, dict):
        return default
    return payload.get(key, default)


def _position_details(positions: dict[str, Any]) -> list[dict[str, object]]:
    details: list[dict[str, object]] = []
    for symbol, payload in sorted(positions.items()):
        if not isinstance(payload, dict):
            continue
        quantity = _money(payload.get("quantity"))
        average_cost = _money(payload.get("average_cost"))
        raw_market_price = payload.get("market_price") or payload.get("price") or payload.get("last_trade_price")
        price_is_estimated = raw_market_price is None
        market_price = _money(average_cost if price_is_estimated else raw_market_price)
        market_value = _money(quantity * market_price)
        unrealized_pnl = _money((market_price - average_cost) * quantity)
        unrealized_return_pct = round(((market_price - average_cost) / average_cost * 100.0), 2) if average_cost else 0.0
        details.append(
            {
                "symbol": str(payload.get("symbol") or symbol).upper(),
                "quantity": quantity,
                "average_cost": average_cost,
                "market_price": market_price,
                "market_value": market_value,
                "unrealized_pnl": unrealized_pnl,
                "unrealized_return_pct": unrealized_return_pct,
                "market_price_source": "estimated_from_cost" if price_is_estimated else "market",
            }
        )
    return details


def _filled_notional(orders: list[dict[str, Any]]) -> float:
    total = 0.0
    for order in orders:
        if str(order.get("status", "")).lower() != "filled":
            continue
        notional = order.get("notional")
        if notional is None:
            notional = float(order.get("filled_qty") or order.get("quantity") or 0) * float(
                order.get("fill_price") or order.get("limit_price") or 0
            )
        total += float(notional or 0)
    return _money(total)


def _order_counts(orders: list[dict[str, Any]]) -> dict[str, int]:
    filled_orders = [order for order in orders if str(order.get("status", "")).lower() == "filled"]
    filled_ids = {
        str(order.get("order_id"))
        for order in filled_orders
        if order.get("order_id")
    }
    pending_ids = {
        str(order.get("order_id"))
        for order in orders
        if str(order.get("status", "")).lower() == "pending" and order.get("order_id") and str(order.get("order_id")) not in filled_ids
    }
    rejected_or_canceled = [
        order
        for order in orders
        if str(order.get("status", "")).lower() in {"rejected", "canceled", "cancelled"}
    ]
    return {
        "order_count": len(orders),
        "filled_order_count": len(filled_ids) if filled_ids else len(filled_orders),
        "pending_order_count": len(pending_ids),
        "rejected_or_canceled_order_count": len(rejected_or_canceled),
    }


def _position_summaries(position_details: list[dict[str, object]]) -> list[str]:
    summaries: list[str] = []
    for item in position_details:
        quantity = f"{float(item.get('quantity') or 0):.8f}".rstrip("0").rstrip(".")
        summaries.append(
            f"{item.get('symbol')} {quantity} 股，成本 ${_money(item.get('average_cost')):,.2f}，"
            f"现价 ${_money(item.get('market_price')):,.2f}，未实现盈亏 ${_money(item.get('unrealized_pnl')):,.2f}"
        )
    return summaries


def build_paper_account_summary(
    *,
    name: str,
    account_type: str,
    run_date: str,
    day_start_path: Path | None,
    day_end_path: Path | None = None,
    account_path: Path | None = None,
    positions_path: Path | None = None,
    orders_log_path: Path | None = None,
    daily_usage_path: Path | None = None,
    equity_curve_path: Path | None = None,
) -> dict[str, object]:
    day_start = _read_json_or(day_start_path, {}) if day_start_path else {}
    day_end = _read_json_or(day_end_path, {}) if day_end_path else {}
    account = _read_json_or(account_path, {}) if account_path else {}
    positions = _field(day_end, "positions", None)
    if not isinstance(positions, dict) and positions_path is not None:
        positions = _read_json_or(positions_path, {})
    if not isinstance(positions, dict):
        positions = {}
    orders = _read_jsonl(orders_log_path) if orders_log_path else []
    daily_usage = _read_json_or(daily_usage_path, {}) if daily_usage_path else {}
    latest_equity = _latest_jsonl(equity_curve_path) if equity_curve_path else {}

    position_details = _position_details(positions)
    positions_market_value = _field(day_end, "positions_market_value", None)
    if positions_market_value is None:
        positions_market_value = sum(float(item.get("market_value") or 0) for item in position_details)

    starting_cash = _money(_field(day_start, "cash", _field(account, "starting_cash")))
    ending_cash = _money(_field(day_end, "cash", _field(account, "cash", starting_cash)))
    starting_equity = _money(_field(day_start, "total_equity", _field(account, "starting_cash", starting_cash)))
    ending_equity = _field(day_end, "total_equity", None)
    if ending_equity is None:
        ending_equity = _field(latest_equity, "total_equity", None)
    if ending_equity is None:
        ending_equity = ending_cash + _money(positions_market_value)
    ending_equity = _money(ending_equity)
    equity_change = _money(ending_equity - starting_equity)
    realized_pnl = _money(_field(day_end, "realized_pnl", _field(account, "realized_pnl")))
    unrealized_pnl = _money(sum(float(item.get("unrealized_pnl") or 0) for item in position_details))
    return_pct = round((equity_change / starting_equity * 100.0), 2) if starting_equity else 0.0
    counts = _order_counts(orders)
    return {
        "name": name,
        "account_type": account_type,
        "date": run_date,
        "starting_cash": starting_cash,
        "ending_cash": ending_cash,
        "cash_change": _money(ending_cash - starting_cash),
        "starting_total_equity": starting_equity,
        "ending_total_equity": ending_equity,
        "total_equity_change": equity_change,
        "total_return_pct": return_pct,
        "realized_pnl": realized_pnl,
        "unrealized_pnl": unrealized_pnl,
        "positions_market_value": _money(positions_market_value),
        "open_position_count": len(positions),
        "open_positions": sorted(positions),
        "open_position_details": position_details,
        "position_summaries": _position_summaries(position_details),
        "filled_notional": _filled_notional(orders),
        "daily_usage": daily_usage if isinstance(daily_usage, dict) else {},
        **counts,
    }


def build_paper_postmarket_summary(
    *,
    run_date: str,
    day_start_path: Path,
    day_end_path: Path,
    orders_log_path: Path,
    daily_usage_path: Path,
) -> dict[str, object]:
    account_summary = build_paper_account_summary(
        name="主模拟盘",
        account_type="main_paper",
        run_date=run_date,
        day_start_path=day_start_path,
        day_end_path=day_end_path,
        orders_log_path=orders_log_path,
        daily_usage_path=daily_usage_path,
    )
    return {
        **account_summary,
        "date": run_date,
        "trading_mode": "paper",
        "account_summaries": [account_summary],
    }


def _format_account_report_lines(account: dict[str, object]) -> list[str]:
    positions = account.get("open_position_details")
    position_lines: list[str] = []
    if isinstance(positions, list):
        for item in positions:
            if not isinstance(item, dict):
                continue
            position_lines.append(
                f"- {item.get('symbol')}：数量 {item.get('quantity')}，成本 ${_money(item.get('average_cost')):,.2f}，"
                f"现价 ${_money(item.get('market_price')):,.2f}，市值 ${_money(item.get('market_value')):,.2f}，"
                f"未实现盈亏 ${_money(item.get('unrealized_pnl')):,.2f}（{float(item.get('unrealized_return_pct') or 0):.2f}%）"
                + ("；价格缺失，按成本暂估" if item.get("market_price_source") == "estimated_from_cost" else "")
            )
    if not position_lines:
        position_lines = ["- 当前没有持仓。"]
    return [
        f"### {account.get('name', '未命名账户')}",
        f"- 期初总权益：${_money(account.get('starting_total_equity')):,.2f}",
        f"- 期末总权益：${_money(account.get('ending_total_equity')):,.2f}",
        f"- 当日收益：${_money(account.get('total_equity_change')):,.2f}（{float(account.get('total_return_pct') or 0):.2f}%）",
        f"- 已实现盈亏：${_money(account.get('realized_pnl')):,.2f}",
        f"- 未实现盈亏：${_money(account.get('unrealized_pnl')):,.2f}",
        f"- 现金：${_money(account.get('ending_cash')):,.2f}",
        f"- 持仓市值：${_money(account.get('positions_market_value')):,.2f}",
        f"- 订单：总数 {int(account.get('order_count', 0) or 0)}，成交 {int(account.get('filled_order_count', 0) or 0)}，"
        f"待成交 {int(account.get('pending_order_count', 0) or 0)}，成交名义金额 ${_money(account.get('filled_notional')):,.2f}",
        "- 持仓明细：",
        *position_lines,
    ]


def build_paper_postmarket_zh_report(summary: dict[str, object]) -> str:
    open_positions = summary.get("open_positions")
    if isinstance(open_positions, list) and open_positions:
        positions_text = "、".join(str(symbol) for symbol in open_positions)
    else:
        positions_text = "无"
    daily_usage = summary.get("daily_usage")
    usage_used = _money(_field(daily_usage, "used_notional")) if isinstance(daily_usage, dict) else 0.0
    usage_paper = _money(_field(daily_usage, "paper_filled_notional")) if isinstance(daily_usage, dict) else 0.0
    usage_orders = int(_field(daily_usage, "paper_order_count")) if isinstance(daily_usage, dict) else 0
    position_detail_lines = [
        (
            f"- {item.get('symbol')}：数量 {item.get('quantity')}，成本 ${_money(item.get('average_cost')):,.2f}，"
            f"现价 ${_money(item.get('market_price')):,.2f}，市值 ${_money(item.get('market_value')):,.2f}，"
            f"未实现盈亏 ${_money(item.get('unrealized_pnl')):,.2f}（{float(item.get('unrealized_return_pct') or 0):.2f}%）"
        )
        for item in summary.get("open_position_details", [])
        if isinstance(item, dict)
    ]
    account_summaries = summary.get("account_summaries")
    account_report_lines: list[str] = []
    if isinstance(account_summaries, list):
        for account in account_summaries:
            if isinstance(account, dict):
                account_report_lines.extend(_format_account_report_lines(account))
                account_report_lines.append("")
    return "\n".join(
        [
            f"# 盘后复盘报告 - {summary.get('date', '')}",
            "",
            "## 账户概览",
            f"- 交易模式：{summary.get('trading_mode', 'paper')}",
            f"- 期初现金：${_money(summary.get('starting_cash')):,.2f}",
            f"- 期末现金：${_money(summary.get('ending_cash')):,.2f}",
            f"- 现金变化：${_money(summary.get('cash_change')):,.2f}",
            f"- 期初总权益：${_money(summary.get('starting_total_equity')):,.2f}",
            f"- 期末总权益：${_money(summary.get('ending_total_equity')):,.2f}",
            f"- 总权益变化：${_money(summary.get('total_equity_change')):,.2f}",
            f"- 已实现盈亏：${_money(summary.get('realized_pnl')):,.2f}",
            f"- 持仓市值：${_money(summary.get('positions_market_value')):,.2f}",
            "",
            "## 交易执行",
            f"- 总订单数：{int(summary.get('order_count', 0) or 0)}",
            f"- 成交订单数：{int(summary.get('filled_order_count', 0) or 0)}",
            f"- 拒绝/取消订单数：{int(summary.get('rejected_or_canceled_order_count', 0) or 0)}",
            f"- 成交名义金额：${_money(summary.get('filled_notional')):,.2f}",
            "",
            "## 风险与额度",
            f"- 当日已用名义金额：${usage_used:,.2f}",
            f"- 模拟盘成交名义金额：${usage_paper:,.2f}",
            f"- 模拟盘订单计数：{usage_orders}",
            "",
            "## 持仓",
            f"- 持仓数量：{int(summary.get('open_position_count', 0) or 0)}",
            f"- 持仓标的：{positions_text}",
            *position_detail_lines,
            "",
            "## 每个账户持仓与收益",
            *(account_report_lines or ["- 未找到独立账户明细。"]),
            "",
            "## 复盘提示",
            "- 若总权益变化与成交记录不一致，先检查 paper/orders.jsonl 与 paper/equity_curve.jsonl。",
            "- 若成交金额接近当日或单笔上限，明天盘前需要降低候选优先级或收紧下单额度。",
            "- 这份报告只用于模拟盘/交易流程复盘，最终风控仍以本地日志、计划文件和账户状态为准。",
            "",
        ]
    )
