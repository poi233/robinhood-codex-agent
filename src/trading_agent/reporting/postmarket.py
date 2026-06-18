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


def _position_details(positions: dict[str, Any]) -> list[dict[str, object]]:
    details: list[dict[str, object]] = []
    for symbol, payload in sorted(positions.items()):
        if not isinstance(payload, dict):
            continue
        quantity = _money(payload.get("quantity"))
        average_cost = _money(payload.get("average_cost"))
        market_price = _money(payload.get("market_price") or payload.get("price") or payload.get("last_trade_price"))
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
            }
        )
    return details


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
        "open_position_details": _position_details(positions),
        "order_count": len(orders),
        "filled_order_count": len(filled_orders),
        "rejected_or_canceled_order_count": len(rejected_orders),
        "filled_notional": _money(sum(float(order.get("notional", 0) or 0) for order in filled_orders)),
        "daily_usage": daily_usage if isinstance(daily_usage, dict) else {},
    }


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
            "## 复盘提示",
            "- 若总权益变化与成交记录不一致，先检查 paper/orders.jsonl 与 paper/equity_curve.jsonl。",
            "- 若成交金额接近当日或单笔上限，明天盘前需要降低候选优先级或收紧下单额度。",
            "- 这份报告只用于模拟盘/交易流程复盘，最终风控仍以本地日志、计划文件和账户状态为准。",
            "",
        ]
    )
