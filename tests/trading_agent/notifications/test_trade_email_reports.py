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
    assert "##" not in body
    assert "- " not in body
    assert "【消息面重点】" in body
    assert "Nvidia expands AI platform" in body
    assert "【可买股票重点】" in body
    assert "NVDA：总分 86.4" in body
    assert "Blackwell 需求继续改善" in body
    assert "【模块运行总结】" in body
    assert "模块数：3；完成 2、跳过 1。" in body
    assert "异常/跳过：kronos：跳过" in body
    assert "最耗时：final_planner 2.0s；account_snapshot 1.2s。" in body
    assert "account_snapshot completed" not in body
    assert "runtime/state/runs/2026-06-17/planner/daily_plan.json" in body


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
    assert "##" not in body
    assert "【当前持仓分析】" in body
    assert "NVDA：数量 1，成本 $100.00，现价 $110.00，市值 $110.00，未实现盈亏 $10.00（10.00%）" in body
    assert "【今日回顾】" in body
    assert "总权益变化 $12.50" in body


def test_build_postmarket_email_body_includes_shadow_experiments() -> None:
    body = build_postmarket_email_body(
        {
            "date": "2026-06-24",
            "trading_mode": "paper",
            "shadow_experiments": [
                {
                    "name": "midfreq_v1__trend_follow",
                    "filled_order_count": 2,
                    "pending_order_count": 0,
                    "position_summaries": ["AMD 76.89 股，成本 $522.31"],
                },
                {
                    "name": "midfreq_v1__gap_fill",
                    "filled_order_count": 0,
                    "pending_order_count": 1,
                    "position_summaries": [],
                },
            ],
        }
    )

    assert "【影子实验盘】" in body
    assert "midfreq_v1__trend_follow：成交 2，待成交 0，持仓 AMD 76.89 股，成本 $522.31。" in body
    assert "midfreq_v1__gap_fill：成交 0，待成交 1，持仓 无。" in body
    assert "不会触发真实订单" in body


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
            advisory_overlay={
                "rank_delta": 5.0,
                "size_multiplier": 0.5,
                "block_buy": False,
                "blocked_reasons": [],
                "components": {
                    "factor_alpha": {"score": 88.0},
                    "ai": {"kronos": {"direction": "long", "confidence": 0.8}},
                    "regime": {"regime": "neutral", "applied_multiplier": 0.5},
                    "portfolio": {"position_weight": 0.04},
                },
            },
        ),
    )

    body = build_intraday_trade_email_body(decision)

    assert body.startswith("【盘中成交通知】")
    assert "##" not in body
    assert "【本次操作】" in body
    assert "模拟盘已买入 NVDA，数量 1，限价 $100.50，名义金额 $100.50。" in body
    assert "【买入原因】" in body
    assert "候选排名通过、价格位于计划入场区间、仓位和风控额度通过" in body
    assert "【风险与价格】" in body
    assert "止损 $98.00" in body
    assert "【辅助信号叠加（advisory overlay）】" in body
    assert "排序调整：+5.00" in body
    assert "仓位乘数：0.50" in body
    assert "量价因子：88.0" in body
    assert "AI·Kronos预测：看多（置信度 0.80）" in body
