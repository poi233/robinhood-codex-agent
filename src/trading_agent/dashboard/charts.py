from __future__ import annotations

import json
import math
from typing import Any

import pandas as pd
import streamlit as st

from trading_agent.dashboard import ui


# --- shared chart helper (themed) -----------------------------------------

def _bar(items: list[tuple[str, float]], *, x_title: str, y_title: str, x_label: str | None = None,
         y_label: str | None = None) -> None:
    cleaned = []
    for label, value in items:
        if value is None:
            continue
        try:
            finite_value = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(finite_value):
            cleaned.append((label, finite_value))
    if not cleaned:
        return
    values = [value for _, value in cleaned]
    if len(cleaned) < 2 or len({round(value, 8) for value in values}) <= 1:
        ui.pretty_table(
            [{y_title: label, x_title: value} for label, value in cleaned],
            rename={y_title: y_label or y_title, x_title: x_label or x_title},
        )
        return
    ui.bar_list(cleaned, value_label=x_label or x_title)


def _line_chart_or_table(df: pd.DataFrame, *, caption: str) -> None:
    if df.empty or len(df.index) < 2:
        st.caption(f"{caption}：数据点不足，暂不绘制趋势图。")
        ui.pretty_table(df.reset_index())
        return
    numeric = df.select_dtypes(include="number")
    if numeric.empty or all(numeric[col].dropna().nunique() <= 1 for col in numeric.columns):
        st.caption(f"{caption}：数值尚无变化，暂不绘制空趋势图。")
        ui.pretty_table(df.reset_index())
        return
    st.line_chart(df, width="stretch")


_PLAN_STATE_LABEL = {"trade_ready": "可交易", "observe_only": "只观察", "no_trade": "不交易", "normal": "正常"}
_MARKET_REGIME_LABEL = {
    "normal": "正常",
    "bull": "多头",
    "neutral": "中性",
    "risk_off": "避险",
    "panic": "恐慌",
    "unknown": "未知",
}


def plan_state_badge(plan_state: str | None) -> str:
    raw = str(plan_state or "").lower()
    label = _PLAN_STATE_LABEL.get(raw)
    if not plan_state:
        return "—"
    return f"{label}（{plan_state}）" if label else str(plan_state)


def market_regime_badge(regime: str | None) -> str:
    raw = str(regime or "").lower()
    label = _MARKET_REGIME_LABEL.get(raw)
    if not regime:
        return "—"
    return f"{label}（{regime}）" if label else str(regime)


def pnl_verdict(value: Any) -> ui.Verdict | None:
    if value is None:
        return None
    try:
        pnl = float(value)
    except (TypeError, ValueError):
        return None
    if pnl > 0:
        return ui.Verdict("good", ui.GOOD, "", "盈利")
    if pnl < 0:
        return ui.Verdict("bad", ui.BAD, "", "亏损")
    return ui.Verdict("neutral", ui.NEUTRAL, "", "持平")


def return_verdict(value: Any) -> ui.Verdict | None:
    if value is None:
        return None
    try:
        ret = float(value)
    except (TypeError, ValueError):
        return None
    if ret > 0:
        return ui.Verdict("good", ui.GOOD, "", "正收益")
    if ret < 0:
        return ui.Verdict("bad", ui.BAD, "", "负收益")
    return ui.Verdict("neutral", ui.NEUTRAL, "", "持平")


def _latest_trading_decision(decisions: list[dict[str, Any]]) -> dict[str, Any] | None:
    trading_decisions = [
        row for row in decisions
        if str(row.get("decision") or "") in {"would_trade", "blocked", "no_trade"}
    ]
    return trading_decisions[-1] if trading_decisions else None


def cockpit_hero(
    overview_delta: dict[str, Any],
    completeness: dict[str, Any],
    regime_payload: dict[str, Any],
    decisions: list[dict[str, Any]],
) -> None:
    curr = overview_delta.get("curr") or {}
    latest = _latest_trading_decision(decisions)
    plan = str(curr.get("plan_state") or "")
    regime = str(curr.get("market_regime") or regime_payload.get("regime") or "")
    completeness_pct = float(completeness.get("pct") or 0)
    tradable = int(curr.get("tradable_count") or 0)
    score = completeness_pct
    if plan == "trade_ready":
        score = min(100, score + 6)
    if latest and latest.get("decision") == "blocked":
        score = max(0, score - 12)

    if latest and latest.get("decision") == "blocked":
        reasons = _norm_reasons(latest.get("blocked_reasons")) or "等待更好入场区"
        headline = "系统准备完毕，但执行层仍在等价格确认"
        copy = f"盘中最新结论是不交易；主要拦截为 {reasons}。当前适合盯入场区，不适合追价。"
    elif latest and latest.get("decision") == "would_trade":
        headline = "出现可交易信号，按计划检查订单约束"
        copy = f"最新可交易标的为 {latest.get('symbol') or '—'}，方向 {latest.get('side') or '—'}。"
    else:
        headline = "盘前计划已生成，等待盘中决策"
        copy = "关键运行产物已就绪；盘中执行会继续检查价格区间、追高和风险约束。"

    ui.hero_panel(
        kicker=f"{market_regime_badge(regime)} · {plan_state_badge(plan)}",
        headline=headline,
        copy=copy,
        score=score,
        score_label="运行评分",
        metrics=[
            ("账户权益", ui.fmt_currency(curr.get("total_equity"))),
            ("观察 / 可交易", f"{curr.get('watchlist_count', 0)} / {tradable}"),
            ("最高评分", ui.fmt_number(curr.get("top_score"))),
            ("数据完整度", ui.fmt_pct(completeness_pct)),
        ],
    )


# ============================================================
# 今日驾驶舱
# ============================================================

def regime_banner(payload: dict) -> None:
    """K2：量化市场状态 + 仓位乘子（advisory）。"""
    if not payload or not payload.get("regime"):
        return
    regime = payload["regime"]
    label = {"bull": "多头", "neutral": "中性", "risk_off": "避险", "panic": "恐慌",
             "unknown": "未知"}.get(regime, regime)
    applied = payload.get("applied_multiplier")
    reasons = "、".join(payload.get("reasons") or []) or "无"
    line = (f"**市场状态：{label}（{regime}）** · 仓位乘子（只降不升）：{applied}× · 依据：{reasons}"
            "　（advisory，尚未接入实际 sizing）")
    if regime in {"risk_off", "panic"}:
        st.warning(line)
    else:
        st.info(line)


def nightly_health_banner(health: dict) -> None:
    """L4：夜间批处理健康度，绿/红横幅，避免静默失败被忽略。"""
    if not health:
        st.info("暂无夜间健康数据。夜间批处理（或 `analytics nightly-health`）会写入。")
        return
    last = health.get("last_nightly_run_date") or "?"
    if health.get("status") == "ok":
        st.success(f"夜间分析正常 · 最近运行 {last} · 所有预期报告新鲜")
        return
    parts = [f"夜间分析需关注 · 最近运行 {last}"]
    if health.get("failed_steps"):
        parts.append("失败步骤：" + "、".join(health["failed_steps"]))
    if health.get("stale_reports"):
        parts.append("过期/缺失报告：" + "、".join(health["stale_reports"]))
    st.error(" · ".join(parts))


def kpi_overview(overview_delta: dict[str, Any]) -> None:
    """今日关键指标卡片，带同比上一交易日 delta + 好坏色。"""
    curr = overview_delta.get("curr") or {}
    prev = overview_delta.get("prev") or {}

    equity = curr.get("total_equity")
    pnl = curr.get("today_pnl")
    pnl_vd = pnl_verdict(pnl)
    prev_label = overview_delta.get("prev_run_date") or "无"
    ui.metric_row([
        ui.MetricCard("计划状态", plan_state_badge(curr.get("plan_state"))),
        ui.MetricCard("市场状态", market_regime_badge(curr.get("market_regime"))),
        ui.MetricCard(
            "观察 / 可交易",
            f"{curr.get('watchlist_count', 0)} / {curr.get('tradable_count', 0)}",
            delta=ui.delta_vs_prev(curr.get("tradable_count"), prev.get("tradable_count")),
            note="可交易标的数 vs 上一交易日",
        ),
        ui.MetricCard(
            "最高综合评分",
            ui.fmt_number(curr.get("top_score")),
            delta=ui.delta_vs_prev(curr.get("top_score"), prev.get("top_score")),
        ),
        ui.MetricCard(
            "账户权益（纸面）",
            ui.fmt_currency(equity),
            delta=ui.delta_vs_prev(equity, prev.get("total_equity")),
        ),
        ui.MetricCard("当日已实现盈亏", ui.fmt_currency(pnl), vd=pnl_vd),
        ui.MetricCard(
            "待成交订单",
            str(curr.get("pending_order_count", 0)),
            delta=ui.delta_vs_prev(curr.get("pending_order_count"), prev.get("pending_order_count")),
        ),
        ui.MetricCard("对比基准日", str(prev_label), note="上一交易日（同比口径）"),
    ])


def data_completeness_view(payload: dict[str, Any]) -> None:
    present = payload.get("present")
    total = payload.get("total")
    pct = payload.get("pct")
    if not total:
        st.info("暂无数据完整度信息。")
        return
    missing = payload.get("missing") or []
    vd = ui.verdict_for("coverage_pct", pct)
    ui.metric_row([
        ui.MetricCard("数据完整度", ui.fmt_pct(pct), vd=vd, note=f"{present}/{total} 项就绪"),
        ui.MetricCard("新闻 / 日线", f"{payload.get('news_count', 0)} / {payload.get('ohlcv_count', 0)}"),
        ui.MetricCard(
            "缺失项",
            str(len(missing)),
            vd=ui.verdict(
                len(missing), good=0, warn=2, higher_is_better=False,
                labels=("齐全", "少量缺口", "缺口较多"),
            ),
        ),
    ])
    if missing:
        st.warning("缺失数据：" + "、".join(f"{row['category']}:{row['artifact']}" for row in missing))
    with st.expander("完整数据项"):
        ui.pretty_table(payload.get("rows") or [])


def today_decision(decisions: list[dict[str, Any]]) -> None:
    trading_decisions = [
        row for row in decisions
        if str(row.get("decision") or "") in {"would_trade", "blocked", "no_trade"}
    ]
    if not trading_decisions:
        st.info("该运行日尚无盘中决策记录。")
        if decisions:
            with st.expander("非交易流程事件"):
                ui.pretty_table(decisions)
        return
    latest = trading_decisions[-1]
    verdict = str(latest.get("decision") or "—")
    if verdict == "would_trade":
        st.success(f"**可交易** — {latest.get('symbol') or ''} {latest.get('side') or ''} "
                   f"（{latest.get('setup_type') or ''}）")
    else:
        reasons = latest.get("blocked_reasons")
        try:
            reasons = "、".join(json.loads(reasons)) if isinstance(reasons, str) else "、".join(reasons or [])
        except Exception:
            pass
        st.warning(f"**不交易** — {reasons or '无'}")
    with st.expander("盘中决策明细"):
        ui.pretty_table(trading_decisions)


def orders_table_view(rows: list[dict[str, Any]]) -> None:
    if not rows:
        st.info("该运行日无纸面订单。")
        return
    ui.pretty_table(rows)


def portfolio_target_view(payload: dict) -> None:
    """K1：当前组合 cash/单仓/主题敞口 vs 目标上限 + 超限告警。"""
    if not payload or payload.get("total_equity") is None:
        st.info("该运行日暂无组合目标（premarket 会从纸面账本写 portfolio_target.json）。")
        return
    t = payload.get("targets") or {}
    sector_cap = t.get("sector_cap")
    sector_cap_str = f" · 行业 ≤ {sector_cap * 100:.0f}%" if sector_cap else ""
    total_equity = payload.get("total_equity")
    cash_weight = payload.get("cash_weight")
    cash_label = f"{cash_weight * 100:.0f}%" if isinstance(cash_weight, (int, float)) else "—"
    st.caption(f"总权益：{ui.fmt_currency(total_equity, digits=0)}　·　现金："
               f"{cash_label}（目标 ≥ {t.get('cash_target', 0) * 100:.0f}%）"
               f"　·　上限：单仓 ≤ {t.get('max_position_size', 0) * 100:.0f}% · "
               f"主题 ≤ {t.get('theme_cap', 0) * 100:.0f}%{sector_cap_str}")
    breaches = payload.get("breaches") or {}
    msgs = []
    if breaches.get("below_cash_target"):
        msgs.append("现金低于目标")
    if breaches.get("oversize_positions"):
        msgs.append("超额单仓：" + "、".join(breaches["oversize_positions"]))
    if breaches.get("overexposed_themes"):
        msgs.append("主题过度集中：" + "、".join(breaches["overexposed_themes"]))
    if breaches.get("overexposed_sectors"):
        msgs.append("行业过度集中：" + "、".join(breaches["overexposed_sectors"]))
    if msgs:
        st.warning("　·　".join(msgs) + "　（advisory，只能收紧、绝不加买入）")
    else:
        st.success("现金与集中度均在目标范围内")
    if payload.get("theme_exposure"):
        st.caption("主题敞口")
        _bar([(k, float(v or 0)) for k, v in payload["theme_exposure"].items()],
             x_title="weight", y_title="theme", x_label="权重", y_label="主题")
    sector_exposure = {k: v for k, v in (payload.get("sector_exposure") or {}).items() if k != "unknown"}
    if sector_exposure:
        st.caption("行业敞口")
        _bar([(k, float(v or 0)) for k, v in sector_exposure.items()],
             x_title="weight", y_title="sector", x_label="权重", y_label="行业")
    if payload.get("position_weights"):
        st.caption("个股权重")
        ui.pretty_table([{"symbol": s, "weight": w} for s, w in payload["position_weights"].items()],
                        rename={"weight": "权重"})


# ============================================================
# 选股与决策
# ============================================================

def candidates_with_rankings_view(rows: list[dict[str, Any]]) -> None:
    if not rows:
        st.info("该运行日无评分候选。")
        return
    top = rows[:8]
    tradable = sum(1 for row in rows if row.get("is_tradable"))
    watchlist = sum(1 for row in rows if row.get("is_watchlist"))
    best = top[0] if top else {}
    ui.metric_row([
        ui.MetricCard("候选数", str(len(rows)), note=f"观察 {watchlist} / 可交易 {tradable}"),
        ui.MetricCard("最高评分", ui.fmt_number(best.get("candidate_score")), note=str(best.get("symbol") or "—")),
        ui.MetricCard("Top 可交易", "、".join(str(r.get("symbol")) for r in top if r.get("is_tradable")) or "—"),
    ])
    ui.pick_cards(top, limit=5)
    ui.pretty_table(
        top,
        columns=[
            "symbol", "candidate_score", "score_status", "is_watchlist", "is_tradable",
            "trade_readiness_score", "advisory_rank_delta",
        ],
        rename={"advisory_rank_delta": "叠加调整(±)"},
    )
    st.caption("「叠加调整(±)」= 基本面/事件/因子/AI/市场状态等辅助层对该票的净排名增量（正=上调，负=下调；空=当日尚无盘中叠加）。")
    with st.expander("完整候选排名与图表"):
        _bar([(row["symbol"], float(row.get("candidate_score") or 0)) for row in rows],
             x_title="candidate_score", y_title="symbol", x_label="综合评分", y_label="标的")
        ui.pretty_table(rows)


def factor_view(payload: dict) -> None:
    symbols = payload.get("symbols") if isinstance(payload, dict) else None
    if not symbols:
        st.info("该运行日暂无价量因子（premarket 在 market_feed OHLCV 就绪后产出 factor_alpha）。")
        return
    st.caption(f"profile：{payload.get('profile', '?')}　·　生成于：{payload.get('generated_at', '?')}")
    cov = payload.get("coverage") or {}
    if cov:
        cov_pct = cov.get("coverage_pct", 0)
        vd = ui.verdict_for("coverage_pct", cov_pct)
        bench_ok = "可用" if cov.get("benchmark_available") else "缺失/过短"
        st.markdown(f"**数据覆盖** {vd.label} — 有日线的标的："
                    f"{cov.get('with_daily_bars', 0)}/{cov.get('active_symbols', 0)}（{cov_pct}%）"
                    f"　·　基准 {cov.get('benchmark', '?')} bar 数：{cov.get('benchmark_bar_count', 0)} {bench_ok}")
        if cov.get("missing_symbols"):
            st.caption("缺日线：" + "、".join(cov["missing_symbols"][:20]))
    rows = []
    for symbol, data in symbols.items():
        rows.append({
            "symbol": symbol,
            "factor_alpha_score": data.get("factor_alpha_score"),
            "coverage": data.get("coverage"),
            "risk_flags": "、".join(data.get("risk_flags") or []),
            **(data.get("factor_components") or {}),
        })
    rows.sort(key=lambda r: (r["factor_alpha_score"] is not None, r["factor_alpha_score"] or 0), reverse=True)
    ui.pretty_table(rows[:8], columns=["symbol", "factor_alpha_score", "coverage", "risk_flags"])
    with st.expander("完整因子明细与图表"):
        _bar([(r["symbol"], float(r["factor_alpha_score"] or 0)) for r in rows],
             x_title="factor_alpha_score", y_title="symbol", x_label="因子α分", y_label="标的")
        ui.pretty_table(rows)


def advisory_overlay_view(rows: list[dict[str, Any]]) -> None:
    if not rows:
        st.info("该运行日暂无叠加审计行。intraday 运行后会写入 rankings 并在此填充。")
        return
    st.caption("只读审计：基础分 + 排名增量 = 最终分；仓位/拦截字段只能收紧风险。")
    ui.pretty_table(rows)
    deltas = [(str(row.get("symbol")), float(row.get("advisory_rank_delta") or 0.0))
              for row in rows if row.get("symbol")]
    if deltas:
        _bar(deltas, x_title="advisory_rank_delta", y_title="symbol",
             x_label="叠加排名增量", y_label="标的")


def decisions_timeline_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        st.info("该运行日无盘中决策记录。")
        return
    ui.pretty_table(rows)


def blocked_reason_trend_view(trend: list[dict[str, Any]]) -> None:
    if not trend:
        st.info("暂无拦截原因历史。")
        return
    ui.pretty_table(trend)


def replay_summary_view(report: dict[str, Any]) -> None:
    if report.get("error"):
        st.warning("暂无回放数据。先跑 premarket + intraday 流程。")
        return
    fill_rate = report.get("fill_rate") or {}
    blocked = report.get("blocked_reasons") or {}
    st.caption(f"区间：{report.get('run_date_count', 0)} 个运行日")

    fr = fill_rate.get("fill_rate_pct", 0)
    nt = blocked.get("no_trade_rate_pct", 0)
    ui.metric_row([
        ui.MetricCard("总订单数", str(fill_rate.get("total_orders", 0))),
        ui.MetricCard("成交率", ui.fmt_pct(fr), vd=ui.verdict_for("fill_rate_pct", fr)),
        ui.MetricCard("评估次数", str(blocked.get("total_evaluations", 0))),
        ui.MetricCard("空仓率", ui.fmt_pct(nt), vd=ui.verdict_for("no_trade_rate_pct", nt)),
    ])

    reason_counts = blocked.get("reason_counts") or {}
    if reason_counts:
        st.markdown("**最常见拦截原因**")
        reason_rows = [
            {"reason": reason, "count": count}
            for reason, count in sorted(reason_counts.items(), key=lambda item: item[1], reverse=True)
        ]
        ui.pretty_table(reason_rows[:5])
        with st.expander("拦截原因图表"):
            _bar([(reason, float(count or 0)) for reason, count in reason_counts.items()],
                 x_title="count", y_title="reason", x_label="次数", y_label="原因")
    by_symbol = fill_rate.get("by_symbol") or {}
    if by_symbol:
        st.markdown("**各标的成交率**")
        ui.pretty_table([{"symbol": symbol, **counts} for symbol, counts in by_symbol.items()])


# ============================================================
# 业绩与对比
# ============================================================

def equity_curve_view(payload: dict[str, Any]) -> None:
    """权益曲线叠加 SPY 基准 + 收益对比卡片。"""
    series = payload.get("series") or []
    if not series:
        st.info("暂无纸面权益历史。")
        return

    strat_ret = payload.get("strategy_return_pct")
    bench_ret = payload.get("benchmark_return_pct")
    strat_vd = return_verdict(strat_ret)
    alpha = (strat_ret - bench_ret) if (strat_ret is not None and bench_ret is not None) else None
    alpha_vd = ui.verdict(alpha, good=0.0, warn=0.0, higher_is_better=True,
                          labels=("跑赢大盘", "持平", "跑输大盘")) if alpha is not None else None
    ui.metric_row([
        ui.MetricCard("策略累计收益", ui.fmt_pct(strat_ret), vd=strat_vd),
        ui.MetricCard(f"基准（{payload.get('benchmark', 'SPY')}）累计收益", ui.fmt_pct(bench_ret)),
        ui.MetricCard(
            "超额收益 (alpha)",
            f"{alpha:+.2f}%" if alpha is not None else "—",
            vd=alpha_vd,
            note="策略 − 基准",
        ),
    ])

    df = pd.DataFrame(series)
    has_bench = "benchmark_equity" in df.columns and df["benchmark_equity"].notna().any()
    plot_cols = ["total_equity"] + (["benchmark_equity"] if has_bench else [])
    rename = {"total_equity": "策略权益", "benchmark_equity": f"{payload.get('benchmark', 'SPY')} 基准"}
    chart_df = df.set_index("timestamp")[plot_cols].rename(columns=rename)
    _line_chart_or_table(chart_df, caption="权益曲线")
    if not has_bench:
        st.caption("（基准曲线需要本地 market_feed 中的 SPY 日线；当前缺数据，只画策略权益）")


def strategy_comparison_view(rows: list[dict[str, Any]]) -> None:
    st.subheader("各策略版本对比（按 strategy_id）")
    if not rows:
        st.info("暂无带 strategy_id 的运行。≥1 个运行被标记 strategy_id 后填充；切到第二个版本后才有真正对比。")
        return
    if len(rows) == 1:
        st.caption("目前只有一个策略版本 — 第二个版本累积运行后才出现并排对比。")
    best = max(rows, key=lambda r: (r.get("total_realized_pnl") or 0))
    enriched = []
    for r in rows:
        row = {"推荐": "最佳" if (r is best and len(rows) > 1) else "", **r}
        enriched.append(row)
    ui.pretty_table(enriched)
    _bar([(row["strategy_id"], float(row.get("fill_rate_pct") or 0)) for row in rows],
         x_title="fill_rate_pct", y_title="strategy_id", x_label="成交率%", y_label="策略版本")


def champion_vs_challengers_view(report: dict[str, Any]) -> None:
    st.subheader("Champion vs 影子挑战者")
    if not report or not report.get("challengers"):
        st.info("暂无影子实验评估。运行：python3 -m trading_agent growth evaluate")
        return
    champion = report.get("champion") or {}
    ui.metric_row([
        ui.MetricCard(
            "Champion 成交率",
            ui.fmt_pct(champion.get("fill_rate_pct", 0)),
            vd=ui.verdict_for("fill_rate_pct", champion.get("fill_rate_pct", 0)),
        ),
        ui.MetricCard(
            "Champion 空仓率",
            ui.fmt_pct(champion.get("no_trade_rate_pct", 0)),
            vd=ui.verdict_for("no_trade_rate_pct", champion.get("no_trade_rate_pct", 0)),
        ),
        ui.MetricCard("Champion 交易天数", str(champion.get("run_date_count", 0))),
    ])
    flat = []
    for chal in report["challengers"]:
        metrics = chal.get("metrics") or {}
        rec = chal.get("recommendation") or {}
        flat.append({
            "challenger": chal.get("challenger_strategy_id"),
            "status": chal.get("status"),
            "shadow_days": metrics.get("shadow_days"),
            "evaluations": metrics.get("total_evaluations"),
            "would_trade": metrics.get("would_trade"),
            "no_trade_rate_pct": metrics.get("no_trade_rate_pct"),
            "recommend_promote": rec.get("recommend_promote"),
            "blocking_reasons": "；".join(rec.get("blocking_reasons") or []),
        })
    ui.pretty_table(flat, rename={
        "challenger": "挑战者", "status": "状态", "shadow_days": "影子天数",
        "evaluations": "评估数", "would_trade": "可交易数", "recommend_promote": "建议升级",
        "blocking_reasons": "阻塞原因",
    })


def _norm_reasons(value: Any) -> str:
    """blocked_reasons may be a JSON string (champion, from DB) or a list (challenger)."""
    if value is None:
        return ""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            return value
    if isinstance(value, list):
        return "、".join(str(v) for v in value)
    return str(value)


def _behavior_cell(cell: dict[str, Any] | None) -> str:
    if not cell:
        return "—"
    dec = str(cell.get("decision") or "")
    if dec == "would_trade":
        return f"买 {cell.get('symbol') or ''} {cell.get('side') or ''}".strip()
    reasons = _norm_reasons(cell.get("blocked_reasons"))
    label = "不交易" if dec in {"blocked", "no_trade", ""} else dec
    return label + (f"（{reasons}）" if reasons else "")


def strategy_equity_replay_view(curves: dict[str, list[dict[str, Any]]]) -> None:
    """各策略权益曲线重放（归一化到 100）+ 收益/最大回撤对比 —— "换成这个策略会怎样"。"""
    curves = {k: v for k, v in (curves or {}).items() if v}
    if not curves:
        st.info("暂无各策略权益数据。champion 来自纸面账本；挑战者来自 experiments/<id> 隔离账本。")
        return
    frames = []
    summary = []
    best_ret = None
    for strat, pts in curves.items():
        vals = [float(p["total_equity"]) for p in pts if p.get("total_equity") is not None]
        if not vals:
            continue
        start = vals[0]
        ser = {str(p["timestamp"]): (float(p["total_equity"]) / start * 100 if start else None)
               for p in pts if p.get("total_equity") is not None}
        frames.append(pd.Series(ser, name=strat))
        ret = (vals[-1] / start - 1) * 100 if start else None
        peak = float("-inf"); mdd = 0.0
        for v in vals:
            peak = max(peak, v)
            if peak > 0:
                mdd = min(mdd, (v / peak - 1) * 100)
        summary.append({"strategy": strat, "return_pct": round(ret, 2) if ret is not None else None,
                        "max_drawdown_pct": round(mdd, 2)})
        if ret is not None and (best_ret is None or ret > best_ret):
            best_ret = ret
    if frames:
        df = pd.concat(frames, axis=1).sort_index().ffill()
        st.caption("归一化净值（每个策略起点=100；越高=该策略在同一段行情里赚得越多）")
        _line_chart_or_table(df, caption="策略权益重放")
    if summary:
        enriched = [{"推荐": "最佳" if (s["return_pct"] == best_ret and len(summary) > 1) else "", **s}
                    for s in summary]
        ui.pretty_table(enriched, rename={"strategy": "策略", "return_pct": "累计收益%",
                                          "max_drawdown_pct": "最大回撤%"})


def strategy_behavior_view(payload: dict[str, Any]) -> None:
    """同一运行日各策略决策行为并排 + 分歧高亮。"""
    rows = payload.get("rows") or []
    strategies = payload.get("strategies") or []
    if not rows:
        st.info("该运行日无决策记录（champion 决策 + 挑战者 shadow_decisions 都为空）。")
        return
    summary = payload.get("summary") or {}
    if summary:
        cards = []
        for strat, s in summary.items():
            div = s.get("diverge_vs_champion", 0)
            vd = ui.verdict(div, good=0, warn=max(1, len(rows) // 3), higher_is_better=False,
                            labels=("与冠军高度一致", "部分分歧", "分歧很大"))
            cards.append(ui.MetricCard(
                strat,
                f"{div} 处分歧",
                vd=vd,
                note=f"出手 {s.get('would_trade', 0)} / {s.get('decisions', 0)} 次 "
                     f"· 冠军出手 {payload.get('champion_would_trade', 0)} 次",
            ))
        ui.metric_row(cards)
    st.caption("每行 = 当天第 N 次决策；“分歧”表示各策略决策不一致。")
    flat = []
    for r in rows:
        cells = r.get("cells") or {}
        flat.append({"#": r.get("index"), "分歧": "是" if r.get("diverge") else "",
                     **{s: _behavior_cell(cells.get(s)) for s in strategies}})
    ui.pretty_table(flat)


# ============================================================
# 校准与归因
# ============================================================

def calibration_view(report: dict) -> None:
    if not report or not report.get("sample_size"):
        st.info("暂无校准数据。运行：python3 -m trading_agent analytics calibrate "
                "（需要网络拉 yfinance；≥15 个运行日后才有意义）。")
        return
    ui.metric_row([
        ui.MetricCard("运行日", str(report.get("run_date_count", 0))),
        ui.MetricCard("样本数", str(report.get("sample_size", 0))),
        ui.MetricCard("Horizon", " / ".join(str(h) for h in (report.get("horizons") or [])) or "—"),
        ui.MetricCard("统计状态", "样本偏少" if report.get("run_date_count", 0) < 15 else "可参考"),
    ])
    if report.get("run_date_count", 0) < 15:
        st.warning("当前只有少量运行日，IC / 胜率只适合观察方向，暂不适合调权重。")
    if report.get("ic_summary"):
        horizon_keys = [str(h) for h in (report.get("horizons") or [])]
        ic_rows = []
        for row in report["ic_summary"]:
            flat = {"分量": row.get("component")}
            for h in horizon_keys:
                stats = (row.get("horizons") or {}).get(h) or {}
                flat[f"{h}天 mean_ic"] = stats.get("mean_ic")
                flat[f"{h}天 t值"] = stats.get("t_stat")
            ic_rows.append(flat)
        if ic_rows:
            ui.pretty_table(ic_rows)

    with st.expander("评分分桶、归因和 near-miss 明细"):
        st.caption(f"生成于：{report.get('generated_at', '?')}")
        st.subheader("评分分桶 vs 远期收益")
        for field, per_h in (report.get("score_buckets") or {}).items():
            for horizon, buckets in per_h.items():
                if not buckets:
                    continue
                st.markdown(f"**{ui.label_of(field)} · {horizon}天**")
                ui.pretty_table(buckets)
                _bar([(f"b{b['bucket']}", float(b["mean_return"] or 0)) for b in buckets],
                     x_title="mean_return", y_title="bucket", x_label="平均收益", y_label="桶")

        st.subheader("分量归因")
        for horizon, rows in (report.get("attribution") or {}).items():
            st.markdown(f"**{horizon}天**")
            ui.pretty_table(rows)

        st.subheader("基准收益")
        bench_rows = [{"benchmark": sym, **{f"{h}天": v.get("mean_return") for h, v in per.items()}}
                      for sym, per in (report.get("benchmarks") or {}).items()]
        if bench_rows:
            ui.pretty_table(bench_rows, rename={"benchmark": "基准"})

        st.subheader("形态结果")
        if report.get("setup_outcomes"):
            ui.pretty_table(report["setup_outcomes"])

        st.subheader("接近门槛 vs 已触发")
        near_rows = []
        for horizon, classes in (report.get("near_miss") or {}).items():
            for cls in ("cleared", "near_miss", "below"):
                data = classes.get(cls) or {}
                near_rows.append({"horizon_天": horizon, "类别": cls, "数量": data.get("count"),
                                  "平均收益": data.get("mean_return"), "命中率": data.get("hit_rate")})
        if near_rows:
            ui.pretty_table(near_rows)


def fill_quality_view(report: dict) -> None:
    if not report or not report.get("fill_count"):
        st.info("暂无成交质量数据。运行：python3 -m trading_agent analytics fill-quality（需要已成交纸面订单）。")
        return
    st.caption(f"生成于：{report.get('generated_at', '?')}　·　成交数：{report.get('fill_count', 0)}"
               f"　·　总名义额：${report.get('total_filled_notional', 0):,.0f}")
    slp = report.get("mean_realized_slippage_bps")
    vd = ui.verdict_for("slippage_bps", slp)
    st.markdown(f"**平均实现滑点** {vd.label} — 全部：{slp}bps · "
                f"买：{report.get('mean_realized_slippage_buy_bps')}bps · "
                f"卖：{report.get('mean_realized_slippage_sell_bps')}bps")
    st.markdown(f"**按桶滑点**（基准：{report.get('bucket_basis', '?')}）")
    if report.get("buckets"):
        ui.pretty_table(report["buckets"])
    st.markdown("**保守成交敏感性** — round-trip edge 缩水 ≈ 假设的 spread；若每轮 edge 小于缩水，"
                "edge 就是乐观成交的假象。")
    if report.get("scenarios"):
        ui.pretty_table(report["scenarios"])


def ai_signal_study_view(report: dict) -> None:
    if not report or not report.get("matched_count"):
        st.info("暂无 AI 信号研究数据。运行：python3 -m trading_agent analytics ai-signal-study "
                "（需跨运行日的 ai_signals.json + 网络拉 yfinance）。")
        return
    st.caption(f"生成于：{report.get('generated_at', '?')}　·　AI 信号：{report.get('ai_signal_count', 0)}"
               f"　·　匹配：{report.get('matched_count', 0)}　·　主 horizon：{report.get('primary_horizon')}天")
    primary = str(report.get("primary_horizon"))
    for layer, data in (report.get("layers") or {}).items():
        if not data.get("signal_count"):
            continue
        acc = data.get("directional_accuracy")
        ic = (data.get("confidence_ic") or {}).get(primary)
        st.markdown(f"**{layer}**（{data['signal_count']} 信号）— 方向准确率："
                    f"{f'{acc * 100:.0f}%' if isinstance(acc, (int, float)) else '—'}　·　置信度 IC："
                    f"{f'{ic:+.2f}' if isinstance(ic, (int, float)) else '—'}")
        buckets = (data.get("confidence_calibration") or {}).get(primary)
        if buckets:
            ui.pretty_table(buckets)
        for label, key in (("理由码", "reason_code_lift"), ("警告码", "warning_code_lift")):
            if data.get(key):
                st.caption(f"{label} 相对基线的 lift")
                ui.pretty_table(data[key])


def ai_ablation_view(report: dict) -> None:
    variants = report.get("variants") or {}
    if not variants or (variants.get("full_ai") or {}).get("n", 0) == 0:
        st.info("暂无 AI 消融数据。运行：python3 -m trading_agent analytics ai-ablation "
                "（需跨运行日的 ai_signals.json + 网络拉 yfinance）。")
        return
    st.caption(f"生成于：{report.get('generated_at', '?')}　·　匹配 symbol-run："
               f"{report.get('matched_symbol_runs', 0)}　·　horizon：{report.get('primary_horizon')}天")
    st.caption("某层 marginal_ic = full_ai IC − 去掉该层的 IC；为正 ⇒ 该层有预测贡献。")
    rows = [{"variant": name, "ic": v.get("ic"), "n": v.get("n"),
             "marginal_ic_of_layer": v.get("marginal_ic_of_layer")} for name, v in variants.items()]
    ui.pretty_table(rows, rename={"variant": "变体", "marginal_ic_of_layer": "该层边际IC"})


def thesis_attribution_view(report: dict[str, Any]) -> None:
    """K3：各投资逻辑的胜率 + 平均收益 — 哪类逻辑真赚钱。"""
    if not report or not report.get("theses"):
        st.info("暂无逻辑归因。运行 `analytics thesis`（或夜间批）生成 thesis_attribution.json。"
                "需 ≥15-30 个运行日才有统计意义。")
        return
    st.caption(f"主 horizon：{report.get('primary_horizon', '?')}天　·　样本：{report.get('sample_size', 0)}"
               f"　·　每逻辑最小样本数：{report.get('min_count', '?')}")
    rows = report["theses"]
    df = pd.DataFrame(rows)
    df["win_rate_pct"] = (df["win_rate"] * 100).round(1)
    df["mean_return_pct"] = (df["mean_return"] * 100).round(2)
    df = df.sort_values("win_rate_pct", ascending=False)
    ui.pretty_table(
        df[["thesis", "win_rate_pct", "mean_return_pct", "count"]],
        rename={"thesis": "投资逻辑", "win_rate_pct": "胜率%", "mean_return_pct": "平均收益%", "count": "样本数"},
    )
    if len(rows) > 1:
        _bar([(r["thesis"], round(r["win_rate"] * 100, 1)) for r in rows],
             x_title="win_rate_pct", y_title="thesis", x_label="胜率%", y_label="投资逻辑")


def thesis_trend_view(series: dict[str, Any]) -> None:
    if not series:
        st.info("暂无逻辑历史。夜间快照会把 thesis_attribution.json 归档到 history/<date>/；"
                "累积几晚后出现趋势。")
        return
    frames = []
    for thesis, points in series.items():
        if not points:
            continue
        df = pd.DataFrame([{"date": p["date"], thesis: round((p["win_rate"] or 0) * 100, 1)}
                           for p in points if p.get("win_rate") is not None])
        if not df.empty:
            frames.append(df.set_index("date"))
    if not frames:
        st.info("暂无可绘制的胜率点。")
        return
    combined = pd.concat(frames, axis=1)
    st.caption("各投资逻辑胜率% 随时间变化（每条线 = 一个逻辑标签）")
    _line_chart_or_table(combined, caption="投资逻辑胜率趋势")


def theme_diagnostics_view(diagnostics: dict[str, Any]) -> None:
    if not diagnostics:
        st.info("该运行日无主题诊断。")
        return
    for bucket, payload in diagnostics.items():
        if not isinstance(payload, dict):
            continue
        st.subheader(f"{bucket}")
        distribution = payload.get("theme_distribution")
        if isinstance(distribution, dict) and distribution:
            _bar([(theme, float(info.get("pct") if isinstance(info, dict) else info or 0))
                  for theme, info in distribution.items()],
                 x_title="pct", y_title="theme", x_label="占比%", y_label="主题")
        details = [{"metric": k, "value": v} for k, v in payload.items() if k != "theme_distribution"]
        if details:
            ui.pretty_table(details, rename={"metric": "指标", "value": "内容"})


# ============================================================
# 成长与趋势
# ============================================================

def growth_observations_view(payload: dict) -> None:
    if not payload:
        st.info("暂无成长观测。运行：python3 -m trading_agent growth observe")
        return
    glob = payload.get("global") or []
    modules = payload.get("modules") or {}
    flat = [{"module": m, **o} for m, obs in modules.items() for o in obs]
    ui.metric_row([
        ui.MetricCard("运行日", str(payload.get("run_date_count", 0))),
        ui.MetricCard("全局问题", str(len(glob))),
        ui.MetricCard("模块问题", str(len(flat))),
    ])
    if not glob and not flat:
        st.success("未检测到问题。")
        return
    with st.expander("成长观测明细"):
        st.caption(f"生成于：{payload.get('generated_at', '?')}")
        if glob:
            st.markdown("**全局**")
            ui.pretty_table(glob)
        if flat:
            st.markdown("**按模块**")
            ui.pretty_table(flat)


def proposals_and_queue_view(proposals: list[dict[str, Any]], queue: list[dict[str, Any]]) -> None:
    st.subheader("提案")
    ui.pretty_table(proposals) if proposals else st.info("尚未写入任何提案。")
    st.subheader("实验队列")
    ui.pretty_table(queue) if queue else st.info("尚未排队任何实验。")


# ============================================================
# K线复盘
# ============================================================

def kline_view(symbol: str, ohlcv: list[dict[str, Any]],
               trades_by_strategy: dict[str, list[dict[str, Any]]],
               *, selected_strategies: list[str] | None = None) -> None:
    """日K + 均线 + 各策略买卖点 + 成交量 + MACD；下方按策略列出成交明细。"""
    if not ohlcv:
        st.info(f"{symbol} 暂无本地日线（market_feed 在 premarket 采集 OHLCV 后即可绘制 K 线）。")
        return
    try:
        from trading_agent.dashboard import kline
    except Exception:
        st.warning("绘制 K 线需要 plotly。安装：`pip install -e \".[dashboard]\"`（含 plotly）。")
        return

    last_close = float(ohlcv[-1].get("close") or 0) if ohlcv else None
    strategies = selected_strategies if selected_strategies is not None else list(trades_by_strategy.keys())
    shown = [s for s in strategies if trades_by_strategy.get(s)]

    # Per-strategy performance cards (round-trip realized P&L / win rate / avg R / open MTM).
    if shown:
        st.markdown("**各策略在该标的的表现对比**")
        cards = []
        for strat in shown:
            s = kline.summarize_strategy_trades(trades_by_strategy.get(strat) or [], last_close)
            realized = s.get("realized_pnl")
            vd = ui.verdict(realized, good=0.0, warn=0.0, higher_is_better=True,
                            labels=("已实现盈利", "持平", "已实现亏损")) if realized is not None else None
            wr = f"胜率 {s['win_rate']}%" if s.get("win_rate") is not None else "无完整回合"
            avg_r = f" · 均 {s['avg_r']}R" if s.get("avg_r") is not None else ""
            unreal = s.get("unrealized_pnl")
            note = f"{wr}{avg_r}"
            if s.get("open_qty"):
                note += f" · 持仓 {s['open_qty']:g}" + (f"（浮动 {unreal:+.2f}）" if unreal is not None else "")
            cards.append(ui.MetricCard(
                f"{strat}",
                ui.fmt_currency(realized) if realized is not None else "—",
                vd=vd,
                note=f"{s['round_trips']} 回合 / {s['trades']} 成交 · {note}",
            ))
        ui.metric_row(cards)

    fig = kline.build_kline_figure(symbol, ohlcv, trades_by_strategy,
                                   selected_strategies=selected_strategies)
    st.plotly_chart(fig, width="stretch", config={"scrollZoom": True, "displaylogo": False})

    if not shown:
        st.caption("所选策略在该标的上暂无成交（买卖点为空）。")
        return
    st.markdown("**成交明细（含交易计划：止损 / 目标 / R:R）**")
    for strat in shown:
        trades = trades_by_strategy.get(strat) or []
        st.markdown(f"**{strat}** — {len(trades)} 笔成交")
        ui.pretty_table(
            [{"date": t["date"], "side": t["side"], "price": t["price"], "quantity": t["quantity"],
              "setup_type": t.get("setup_type"), "stop_price": t.get("stop_price"),
              "target_1": t.get("target_1"), "reward_risk": t.get("reward_risk"),
              "slippage_bps": t.get("slippage_bps"), "reason": t["reason"]} for t in trades],
            rename={"date": "日期", "side": "方向", "price": "成交价", "quantity": "数量",
                    "setup_type": "形态", "stop_price": "止损", "target_1": "目标1",
                    "reward_risk": "R:R", "slippage_bps": "滑点bps", "reason": "理由"},
        )


def symbol_behavior_view(decisions_by_strategy: dict[str, list[dict[str, Any]]]) -> None:
    """各策略对该标的的决策行为（含未成交的 would_trade / 被拦截的尝试）。"""
    data = {k: v for k, v in (decisions_by_strategy or {}).items() if v}
    if not data:
        st.caption("各策略对该标的暂无决策记录（除了上面已成交的买卖点）。")
        return
    st.markdown("**各策略对该标的的决策行为**（不止成交：含 would_trade 尝试与被拦截原因）")
    for strat, rows in data.items():
        wt = sum(1 for r in rows if str(r.get("decision")) == "would_trade")
        st.markdown(f"**{strat}** — {len(rows)} 次涉及该标的的决策 · 其中出手 {wt} 次")
        ui.pretty_table(
            [{"run_date": r.get("run_date"), "decision": r.get("decision"), "side": r.get("side"),
              "blocked_reasons": _norm_reasons(r.get("blocked_reasons"))} for r in rows],
            rename={"run_date": "运行日", "decision": "决策", "side": "方向", "blocked_reasons": "拦截原因"},
        )


def trends_view(history_dates: list, snapshot: dict, trend: dict) -> None:
    """I4：数据新鲜度 + 按日快照回看 + 夜间快照趋势线。"""
    if history_dates:
        latest = history_dates[0]
        gen = (snapshot or {}).get("generated_at", "?")
        st.success(f"最近夜间分析：**{latest}**（生成于：{gen}）")
    else:
        st.info("暂无夜间快照。运行：python3 -m trading_agent analytics snapshot "
                "（或夜间批 src/scripts/entrypoints/run_nightly_analysis.sh）。")

    if snapshot:
        st.subheader("所选日期的快照")
        headline = {k: snapshot.get(k) for k in
                    ("fill_rate_pct", "no_trade_rate_pct", "calibration_sample_size",
                     "proposal_count", "active_shadow_count")}
        ui.pretty_table([headline], rename={
            "calibration_sample_size": "校准样本数", "proposal_count": "提案数",
            "active_shadow_count": "活跃影子数"})
        if snapshot.get("top_component_ic"):
            ic_rows = [{"horizon": f"{h}天", "component": v.get("component"), "ic": v.get("ic")}
                       for h, v in snapshot["top_component_ic"].items()]
            st.caption("当晚最强分量 IC")
            ui.pretty_table(ic_rows, rename={"component": "分量"})

    st.subheader("跨夜间快照的趋势")
    if not trend or trend.get("status") != "ok":
        st.info("快照不足以出趋势（需 ≥1 晚）。多日跑夜间批，或每天跑 `analytics snapshot`。")
        return
    series = trend.get("series") or {}
    for metric, points in series.items():
        if not points:
            continue
        df = pd.DataFrame(points).set_index("date")[["value"]].rename(columns={"value": ui.label_of(str(metric))})
        st.caption(ui.label_of(str(metric)))
        _line_chart_or_table(df, caption=ui.label_of(str(metric)))


# ── O3: selection layer (weekly screener O1 + daily dynamic active O2) ──────────────────
def screener_change_view(payload: dict[str, Any]) -> None:
    """O1: the latest weekly universe change — what the screener added / demoted / skipped."""
    if not payload or not payload.get("change"):
        st.info(
            "暂无每周选股记录。运行 `python3 -m trading_agent screen`（或周日 cron）后会生成 "
            "`runtime/screener/<date>/universe_change.json`（`screen --dry-run` 仅出报告、不改 universe）。"
        )
        return
    change = payload["change"]
    status = payload.get("status") or {}
    applied = change.get("applied")
    st.caption(
        f"最近一次：{payload.get('date', '?')}　·　模式：{'✅ 已应用' if applied else '📝 仅报告'}"
        f"　·　发现 {status.get('discovered_count', '?')} 只"
        f"　·　effective {change.get('effective_count_before', '?')}→{change.get('effective_count_after', '?')}"
    )
    added = change.get("added") or []
    if added:
        st.write(f"**新增 {len(added)} 只**（按因子分）")
        ui.pretty_table(
            added,
            columns=["symbol", "factor_score", "theme", "thesis"],
            rename={"symbol": "代码", "factor_score": "因子分", "theme": "主题", "thesis": "逻辑"},
        )
    else:
        st.write("本期无新增。")
    demoted = change.get("demoted") or []
    if demoted:
        st.caption("⬇️ 降级为 passive（超上限，仍留在池中、未删）：" + ", ".join(demoted))
    skipped = change.get("skipped") or []
    if skipped:
        with st.expander(f"跳过的发现（{len(skipped)}）"):
            ui.pretty_table(skipped, columns=["symbol", "reason"], rename={"symbol": "代码", "reason": "原因"})


def active_selection_view(payload: dict[str, Any]) -> None:
    """O2: today's dynamic active set — pins ∪ top-N universe by screen_score."""
    if not payload or not payload.get("active"):
        st.info(
            "暂无动态 active 选择。premarket 运行后会写 "
            "`planner/active_selection.json`（pin 锚 ∪ 按 screen_score 选出的 top-N）。"
        )
        return
    active = payload.get("active") or []
    pins = payload.get("pins") or []
    from_screen = payload.get("from_screen") or []
    st.caption(
        f"今日 active {len(active)} 只　·　pin 锚 {len(pins)}　·　screen 补 {len(from_screen)}"
        f"　·　ACTIVE_MAX {payload.get('active_max', '?')}　·　universe {payload.get('universe_size', '?')}"
    )
    if from_screen:
        st.write("**靠 screen_score 选进来的**")
        ui.pretty_table(
            from_screen, columns=["symbol", "screen_score"], rename={"symbol": "代码", "screen_score": "因子分"}
        )
    if pins:
        st.write("**pin 锚（永含）**：" + ", ".join(pins))


_QUALITY_FLAG_ZH = {
    "unprofitable": "不盈利",
    "negative_roe": "ROE为负",
    "revenue_declining": "营收下滑",
    "high_leverage": "高杠杆",
    "weak_liquidity": "流动性弱",
}
_EVENT_FLAG_ZH = {
    "earnings_imminent": "临近财报",
    "analyst_bullish": "分析师看多",
    "analyst_bearish": "分析师看空",
    "estimate_revised_up": "预期上修",
    "estimate_revised_down": "预期下修",
}


def fundamental_event_view(rows: list[dict[str, Any]]) -> None:
    """H7/H8: per-symbol fundamental quality + earnings/analyst event flags.
    Both now tighten the intraday advisory rank, so this explains why a candidate may be demoted."""
    if not rows:
        st.info(
            "暂无基本面/事件数据。premarket 的 H7 基本面层与 H8 事件层会写 "
            "`signals/fundamental_snapshot.json` 与 `planner/event_snapshot.json`（数据源 yfinance，best-effort）。"
        )
        return
    table = []
    for row in rows:
        qflags = [_QUALITY_FLAG_ZH.get(f, f) for f in (row.get("quality_flags") or [])]
        eflags = [_EVENT_FLAG_ZH.get(f, f) for f in (row.get("event_flags") or [])]
        dte = row.get("days_to_earnings")
        table.append({
            "代码": row.get("symbol"),
            "基本面": "、".join(qflags) if qflags else "合格",
            "距财报(天)": dte if dte is not None else "—",
            "事件": "、".join(eflags) if eflags else "无",
        })
    st.caption("基本面与事件均为风险/谨慎过滤：弱基本面或临近财报会下调候选排名，绝不单独构成买入信号。")
    ui.pretty_table(table, columns=["代码", "基本面", "距财报(天)", "事件"])


# ── O4: selection-layer effectiveness ──────────────────────────────────────────────────
def screen_eval_view(report: dict[str, Any]) -> None:
    """O4: did the screener's picks actually work — added/demoted forward returns + screen_score IC."""
    if not report or report.get("status") != "ok":
        st.info(
            "暂无选股有效性数据。每周选股跑几周、有未来价格 bar 后，运行 "
            "`analytics screen-eval`（或夜间批）会算：新增票超额收益、被降级票表现、screen_score Rank IC。"
        )
        return
    st.caption(
        f"基准 {report.get('benchmark', 'SPY')}　·　screener 运行 {report.get('screener_runs', 0)} 次"
        f"　·　新增 {report.get('added_count', 0)}（匹配 {report.get('added_matched', 0)}）"
        f"　·　降级 {report.get('demoted_count', 0)}"
    )
    added = report.get("added") or {}
    if added:
        st.write("**新增票 forward return（vs 基准超额）**")
        ui.pretty_table(
            [{"horizon": f"{h}d", **row} for h, row in added.items()],
            columns=["horizon", "count", "mean_return", "mean_excess_vs_benchmark", "win_rate_vs_benchmark"],
            rename={"horizon": "周期", "count": "样本", "mean_return": "平均收益",
                    "mean_excess_vs_benchmark": "平均超额", "win_rate_vs_benchmark": "跑赢基准率"},
        )
    ic = report.get("screen_score_ic") or {}
    if ic:
        st.write("**screen_score Rank IC（越高越能预测前向收益）**")
        ui.pretty_table(
            [{"horizon": f"{h}d", "ic": row.get("ic"), "n": row.get("n")} for h, row in ic.items()],
            columns=["horizon", "ic", "n"],
            rename={"horizon": "周期", "ic": "IC", "n": "样本"},
        )
    demoted = report.get("demoted") or {}
    if demoted and report.get("demoted_count"):
        with st.expander("被降级票 forward return（期望偏弱）"):
            ui.pretty_table(
                [{"horizon": f"{h}d", **row} for h, row in demoted.items()],
                columns=["horizon", "count", "mean_return", "mean_excess_vs_benchmark"],
                rename={"horizon": "周期", "count": "样本", "mean_return": "平均收益",
                        "mean_excess_vs_benchmark": "平均超额"},
            )
