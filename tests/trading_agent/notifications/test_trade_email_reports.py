from __future__ import annotations

import json
from pathlib import Path

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import write_json
from trading_agent.notifications.trade_email_reports import (
    build_intraday_trade_email_body,
    build_postmarket_email_body,
    build_premarket_email_body,
)
from trading_agent.policy.models import OrderIntent, PolicyDecision


def _append_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def test_build_premarket_email_body_includes_news_buy_candidates_and_module_runtime(tmp_path: Path) -> None:
    paths = build_runtime_paths(tmp_path, run_date="2026-06-17")
    write_json(
        paths.daily_plan_path,
        {
            "date": "2026-06-17",
            "plan_state": "trade_ready",
            "market_regime": "normal",
            "allowed_actions": ["small_limit_buy"],
            "today_watchlist": ["NVDA"],
        },
    )
    write_json(
        paths.candidate_scores_path,
        {"symbols": {"NVDA": {"total_score": 86.4, "components": {"technical": 80, "catalyst": 75}}}},
    )
    write_json(
        paths.risk_overlay_path,
        {
            "tradable_candidates": ["NVDA"],
            "symbol_trade_rules": {"NVDA": {"allow_buy": True, "max_notional": 1200}},
        },
    )
    write_json(
        paths.catalyst_snapshot_path,
        {"symbols": {"NVDA": {"catalysts": ["Blackwell 需求继续改善"], "risk_flags": ["估值偏高"]}}},
    )
    write_json(
        paths.market_feed_dir / "news" / "NVDA.json",
        {"headlines": [{"title": "Nvidia expands AI platform", "source": "Reuters"}]},
    )
    _append_jsonl(
        paths.run_logs_dir / "pipeline" / "pipeline.jsonl",
        [
            {"stage": "account_snapshot", "status": "completed", "elapsed_seconds": 1.234, "message": "account_snapshot completed"},
            {"stage": "kronos", "status": "skipped", "message": "Kronos signal layer disabled"},
            {"stage": "final_planner", "status": "completed", "elapsed_seconds": 2.0, "message": "final_planner completed"},
        ],
    )

    body = build_premarket_email_body(tmp_path, run_date="2026-06-17")

    assert body.startswith("【盘前计划通知】")
    assert "## 消息面重点" in body
    assert "Nvidia expands AI platform" in body
    assert "## 可买股票重点" in body
    assert "NVDA：总分 86.4" in body
    assert "Blackwell 需求继续改善" in body
    assert "## 模块运行总结" in body
    assert "account_snapshot：完成，耗时 1.23 秒" in body
    assert "kronos：跳过" in body


def test_build_postmarket_email_body_includes_current_position_analysis_and_review() -> None:
    body = build_postmarket_email_body(
        {
            "date": "2026-06-17",
            "trading_mode": "paper",
            "starting_total_equity": 1000,
            "ending_total_equity": 1012.5,
            "total_equity_change": 12.5,
            "realized_pnl": 2.0,
            "order_count": 1,
            "filled_order_count": 1,
            "filled_notional": 110,
            "open_position_count": 1,
            "open_position_details": [
                {
                    "symbol": "NVDA",
                    "quantity": 1,
                    "average_cost": 100,
                    "market_price": 110,
                    "market_value": 110,
                    "unrealized_pnl": 10,
                    "unrealized_return_pct": 10,
                }
            ],
        }
    )

    assert body.startswith("【盘后复盘通知】")
    assert "## 当前持仓分析" in body
    assert "NVDA：数量 1，成本 $100.00，现价 $110.00，市值 $110.00，未实现盈亏 $10.00（10.00%）" in body
    assert "## 今日回顾" in body
    assert "总权益变化 $12.50" in body


def test_build_intraday_trade_email_body_explains_buy_operation_in_chinese() -> None:
    decision = PolicyDecision(
        trading_mode="paper",
        checked_symbols=["NVDA"],
        decision="would_trade",
        action_taken="paper_fill",
        intent=OrderIntent(
            symbol="NVDA",
            side="buy",
            order_type="limit",
            limit_price=100.5,
            estimated_notional=100.5,
            quantity=1,
            setup_type="pullback",
            stop_price=98.0,
            target_1=104.0,
            target_2=108.0,
            reward_risk=2.0,
            reason_codes=["candidate_ranked", "entry_zone_ok", "risk_sizing_ok"],
            confidence=0.72,
        ),
    )

    body = build_intraday_trade_email_body(decision)

    assert body.startswith("【盘中成交通知】")
    assert "## 本次操作" in body
    assert "模拟盘已买入 NVDA，数量 1，限价 $100.50，名义金额 $100.50。" in body
    assert "## 买入原因" in body
    assert "候选排名通过、价格位于计划入场区间、仓位和风控额度通过" in body
    assert "## 风险与价格" in body
    assert "止损 $98.00" in body
