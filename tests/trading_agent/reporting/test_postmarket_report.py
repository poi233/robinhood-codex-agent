from __future__ import annotations

from trading_agent.reporting.postmarket import build_paper_postmarket_zh_report


def test_build_paper_postmarket_zh_report_contains_core_sections() -> None:
    report = build_paper_postmarket_zh_report(
        {
            "date": "2026-06-14",
            "trading_mode": "paper",
            "starting_cash": 1000,
            "ending_cash": 980,
            "cash_change": -20,
            "starting_total_equity": 1000,
            "ending_total_equity": 1010,
            "total_equity_change": 10,
            "realized_pnl": 2,
            "positions_market_value": 30,
            "order_count": 1,
            "filled_order_count": 1,
            "rejected_or_canceled_order_count": 0,
            "filled_notional": 20,
            "open_position_count": 1,
            "open_positions": ["NVDA"],
            "daily_usage": {"used_notional": 20, "paper_filled_notional": 20, "paper_order_count": 1},
        }
    )

    assert "# 盘后复盘报告 - 2026-06-14" in report
    assert "## 交易执行" in report
    assert "持仓标的：NVDA" in report
