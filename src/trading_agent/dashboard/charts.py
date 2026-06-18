from __future__ import annotations

import json
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from trading_agent.dashboard import ui


# --- shared chart helper (themed) -----------------------------------------

def _bar(items: list[tuple[str, float]], *, x_title: str, y_title: str, x_label: str | None = None,
         y_label: str | None = None) -> None:
    if not items:
        return
    frame = pd.DataFrame(items, columns=[y_title, x_title])
    chart = (
        alt.Chart(frame)
        .mark_bar(cornerRadiusEnd=3)
        .encode(
            x=alt.X(f"{x_title}:Q", title=x_label or x_title),
            y=alt.Y(f"{y_title}:N", title=y_label or y_title, sort="-x"),
            tooltip=[alt.Tooltip(f"{y_title}:N", title=y_label or y_title),
                     alt.Tooltip(f"{x_title}:Q", title=x_label or x_title)],
        )
        .properties(height=max(200, 28 * len(frame)))
    )
    st.altair_chart(chart, use_container_width=True)


_PLAN_STATE_ICON = {"trade_ready": "🟢", "observe_only": "🟡", "no_trade": "🔴", "normal": "🟢"}


def plan_state_badge(plan_state: str | None) -> str:
    icon = _PLAN_STATE_ICON.get(str(plan_state or "").lower(), "⚪")
    return f"{icon} {plan_state or '—'}"


# ============================================================
# 📊 今日驾驶舱
# ============================================================

def regime_banner(payload: dict) -> None:
    """K2：量化市场状态 + 仓位乘子（advisory）。"""
    if not payload or not payload.get("regime"):
        return
    regime = payload["regime"]
    emoji = {"bull": "🟢", "neutral": "⚪", "risk_off": "🟠", "panic": "🔴", "unknown": "⚫"}.get(regime, "")
    label = {"bull": "多头", "neutral": "中性", "risk_off": "避险", "panic": "恐慌",
             "unknown": "未知"}.get(regime, regime)
    applied = payload.get("applied_multiplier")
    reasons = "、".join(payload.get("reasons") or []) or "无"
    line = (f"{emoji} **市场状态：{label}（{regime}）** · 仓位乘子（只降不升）：{applied}× · 依据：{reasons}"
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
        st.success(f"🟢 夜间分析正常 · 最近运行 {last} · 所有预期报告新鲜")
        return
    parts = [f"🔴 夜间分析需关注 · 最近运行 {last}"]
    if health.get("failed_steps"):
        parts.append("失败步骤：" + "、".join(health["failed_steps"]))
    if health.get("stale_reports"):
        parts.append("过期/缺失报告：" + "、".join(health["stale_reports"]))
    st.error(" · ".join(parts))


def kpi_overview(overview_delta: dict[str, Any]) -> None:
    """今日关键指标卡片，带同比上一交易日 delta + 好坏色。"""
    curr = overview_delta.get("curr") or {}
    prev = overview_delta.get("prev") or {}

    row1 = st.columns(4)
    ui.kpi_card(row1[0], "计划状态", plan_state_badge(curr.get("plan_state")))
    ui.kpi_card(row1[1], "市场状态", curr.get("market_regime") or "—")
    ui.kpi_card(
        row1[2], "观察 / 可交易",
        f"{curr.get('watchlist_count', 0)} / {curr.get('tradable_count', 0)}",
        delta=ui.delta_vs_prev(curr.get("tradable_count"), prev.get("tradable_count")),
        note="可交易标的数 vs 上一交易日",
    )
    ui.kpi_card(
        row1[3], "最高综合评分",
        ui.fmt_number(curr.get("top_score")),
        delta=ui.delta_vs_prev(curr.get("top_score"), prev.get("top_score")),
    )

    row2 = st.columns(4)
    equity = curr.get("total_equity")
    ui.kpi_card(
        row2[0], "账户权益（纸面）", ui.fmt_currency(equity),
        delta=ui.delta_vs_prev(equity, prev.get("total_equity")),
    )
    pnl = curr.get("today_pnl")
    pnl_vd = ui.verdict(pnl, good=0.0, warn=0.0, higher_is_better=True,
                        labels=("盈利", "持平", "亏损")) if pnl is not None else None
    ui.kpi_card(row2[1], "当日已实现盈亏", ui.fmt_currency(pnl), vd=pnl_vd)
    ui.kpi_card(
        row2[2], "待成交订单", str(curr.get("pending_order_count", 0)),
        delta=ui.delta_vs_prev(curr.get("pending_order_count"), prev.get("pending_order_count")),
    )
    prev_label = overview_delta.get("prev_run_date") or "无"
    ui.kpi_card(row2[3], "对比基准日", str(prev_label), note="上一交易日（同比口径）")


def today_decision(decisions: list[dict[str, Any]]) -> None:
    st.subheader("今天为什么交易 / 不交易")
    if not decisions:
        st.info("该运行日尚无盘中决策记录。")
        return
    latest = decisions[-1]
    verdict = str(latest.get("decision") or "—")
    if verdict == "would_trade":
        st.success(f"✅ **可交易** — {latest.get('symbol') or ''} {latest.get('side') or ''} "
                   f"（{latest.get('setup_type') or ''}）")
    else:
        reasons = latest.get("blocked_reasons")
        try:
            reasons = "、".join(json.loads(reasons)) if isinstance(reasons, str) else "、".join(reasons or [])
        except Exception:
            pass
        st.warning(f"⛔ **{verdict}** — 拦截原因：{reasons or '无'}")
    ui.pretty_table(decisions)


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
    st.caption(f"总权益：${payload.get('total_equity', 0):,.0f}　·　现金："
               f"{payload.get('cash_weight', 0) * 100:.0f}%（目标 ≥ {t.get('cash_target', 0) * 100:.0f}%）"
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
        st.warning("⚠️ " + "　·　".join(msgs) + "　（advisory，只能收紧、绝不加买入）")
    else:
        st.success("🟢 现金与集中度均在目标范围内")
    if payload.get("theme_exposure"):
        st.caption("主题敞口")
        st.bar_chart({k: v for k, v in payload["theme_exposure"].items()})
    sector_exposure = {k: v for k, v in (payload.get("sector_exposure") or {}).items() if k != "unknown"}
    if sector_exposure:
        st.caption("行业敞口")
        st.bar_chart(sector_exposure)
    if payload.get("position_weights"):
        st.caption("个股权重")
        ui.pretty_table([{"symbol": s, "weight": w} for s, w in payload["position_weights"].items()],
                        rename={"weight": "权重"})


# ============================================================
# 🎯 选股与决策
# ============================================================

def candidates_with_rankings_view(rows: list[dict[str, Any]]) -> None:
    if not rows:
        st.info("该运行日无评分候选。")
        return
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
        bench_ok = "✅" if cov.get("benchmark_available") else "⚠️ 缺失/过短"
        st.markdown(f"**数据覆盖** {vd.emoji} {vd.label} — 有日线的标的："
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
    _bar([(r["symbol"], float(r["factor_alpha_score"] or 0)) for r in rows],
         x_title="factor_alpha_score", y_title="symbol", x_label="因子α分", y_label="标的")
    ui.pretty_table(rows)


def advisory_overlay_view(rows: list[dict[str, Any]]) -> None:
    if not rows:
        st.info("该运行日暂无叠加审计行。需 intraday 在 ENABLE_INTRADAY_ADVISORY_OVERLAY=1 下写 rankings 后填充。")
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
    cols = st.columns(4)
    ui.kpi_card(cols[0], "总订单数", str(fill_rate.get("total_orders", 0)))
    ui.kpi_card(cols[1], "成交率", ui.fmt_pct(fr), vd=ui.verdict_for("fill_rate_pct", fr))
    ui.kpi_card(cols[2], "评估次数", str(blocked.get("total_evaluations", 0)))
    ui.kpi_card(cols[3], "空仓率", ui.fmt_pct(nt), vd=ui.verdict_for("no_trade_rate_pct", nt))

    reason_counts = blocked.get("reason_counts") or {}
    if reason_counts:
        st.markdown("**最常见拦截原因**")
        _bar([(reason, float(count or 0)) for reason, count in reason_counts.items()],
             x_title="count", y_title="reason", x_label="次数", y_label="原因")
    by_symbol = fill_rate.get("by_symbol") or {}
    if by_symbol:
        st.markdown("**各标的成交率**")
        ui.pretty_table([{"symbol": symbol, **counts} for symbol, counts in by_symbol.items()])


# ============================================================
# 💰 业绩与对比
# ============================================================

def equity_curve_view(payload: dict[str, Any]) -> None:
    """权益曲线叠加 SPY 基准 + 收益对比卡片。"""
    series = payload.get("series") or []
    if not series:
        st.info("暂无纸面权益历史。")
        return

    strat_ret = payload.get("strategy_return_pct")
    bench_ret = payload.get("benchmark_return_pct")
    cols = st.columns(3)
    strat_vd = ui.verdict(strat_ret, good=0.0, warn=0.0, higher_is_better=True,
                          labels=("正收益", "持平", "负收益")) if strat_ret is not None else None
    ui.kpi_card(cols[0], "策略累计收益", ui.fmt_pct(strat_ret), vd=strat_vd)
    ui.kpi_card(cols[1], f"基准（{payload.get('benchmark', 'SPY')}）累计收益", ui.fmt_pct(bench_ret))
    alpha = (strat_ret - bench_ret) if (strat_ret is not None and bench_ret is not None) else None
    alpha_vd = ui.verdict(alpha, good=0.0, warn=0.0, higher_is_better=True,
                          labels=("跑赢大盘", "持平", "跑输大盘")) if alpha is not None else None
    ui.kpi_card(cols[2], "超额收益 (alpha)",
                f"{alpha:+.2f}%" if alpha is not None else "—", vd=alpha_vd,
                note="策略 − 基准")

    df = pd.DataFrame(series)
    has_bench = "benchmark_equity" in df.columns and df["benchmark_equity"].notna().any()
    plot_cols = ["total_equity"] + (["benchmark_equity"] if has_bench else [])
    rename = {"total_equity": "策略权益", "benchmark_equity": f"{payload.get('benchmark', 'SPY')} 基准"}
    chart_df = df.set_index("timestamp")[plot_cols].rename(columns=rename)
    st.line_chart(chart_df, use_container_width=True)
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
        row = {"推荐": "⭐" if (r is best and len(rows) > 1) else "", **r}
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
    cols = st.columns(3)
    ui.kpi_card(cols[0], "Champion 成交率", ui.fmt_pct(champion.get("fill_rate_pct", 0)),
                vd=ui.verdict_for("fill_rate_pct", champion.get("fill_rate_pct", 0)))
    ui.kpi_card(cols[1], "Champion 空仓率", ui.fmt_pct(champion.get("no_trade_rate_pct", 0)),
                vd=ui.verdict_for("no_trade_rate_pct", champion.get("no_trade_rate_pct", 0)))
    ui.kpi_card(cols[2], "Champion 交易天数", str(champion.get("run_date_count", 0)))
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


# ============================================================
# 🔬 校准与归因
# ============================================================

def calibration_view(report: dict) -> None:
    if not report or not report.get("sample_size"):
        st.info("暂无校准数据。运行：python3 -m trading_agent analytics calibrate "
                "（需要网络拉 yfinance；≥15 个运行日后才有意义）。")
        return
    st.caption(f"生成于：{report.get('generated_at', '?')}　·　运行日：{report.get('run_date_count', 0)}"
               f"　·　样本：{report.get('sample_size', 0)}　·　horizon(天)：{report.get('horizons')}")
    st.warning("小样本噪音大 — 桶单调性 / IC 在 15–30 个运行日后才可信。")

    st.subheader("评分分桶 vs 远期收益")
    for field, per_h in (report.get("score_buckets") or {}).items():
        for horizon, buckets in per_h.items():
            if not buckets:
                continue
            st.markdown(f"**{ui.label_of(field)} · {horizon}天**（评分越高 → 收益越高吗？）")
            ui.pretty_table(buckets)
            st.bar_chart({f"b{b['bucket']}": b["mean_return"] for b in buckets})

    st.subheader("分量归因（Spearman IC，排序）")
    for horizon, rows in (report.get("attribution") or {}).items():
        st.markdown(f"**{horizon}天**")
        ui.pretty_table(rows)

    if report.get("ic_summary"):
        st.subheader("多 horizon Rank IC（逐运行日均值 ± t 统计量）")
        st.caption("均值 = 各运行日横截面 IC 的平均；|t| ≳ 2（在足够多运行日上）⇒ 信号真实、非噪音。")
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

    st.subheader("基准收益（alpha vs beta）")
    bench_rows = [{"benchmark": sym, **{f"{h}天": v.get("mean_return") for h, v in per.items()}}
                  for sym, per in (report.get("benchmarks") or {}).items()]
    if bench_rows:
        ui.pretty_table(bench_rows, rename={"benchmark": "基准"})

    st.subheader("形态结果（先到 target_1 还是先止损）")
    if report.get("setup_outcomes"):
        ui.pretty_table(report["setup_outcomes"])

    st.subheader("接近门槛 vs 已触发（门槛是否过严？）")
    st.caption("若 near_miss 收益 ≈ 或 > cleared，降低 trade_threshold 可能正在错过赢家。")
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
    st.markdown(f"**平均实现滑点** {vd.emoji} {vd.label} — 全部：{slp}bps · "
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
    st.line_chart(combined, use_container_width=True)


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
        st.json({k: v for k, v in payload.items() if k != "theme_distribution"})


# ============================================================
# 🌱 成长与趋势
# ============================================================

def growth_observations_view(payload: dict) -> None:
    if not payload:
        st.info("暂无成长观测。运行：python3 -m trading_agent growth observe")
        return
    st.caption(f"生成于：{payload.get('generated_at', '?')}　·　运行日：{payload.get('run_date_count', 0)}")
    glob = payload.get("global") or []
    if glob:
        st.markdown("**全局**")
        ui.pretty_table(glob)
    modules = payload.get("modules") or {}
    flat = [{"module": m, **o} for m, obs in modules.items() for o in obs]
    if flat:
        st.markdown("**按模块**")
        ui.pretty_table(flat)
    if not glob and not flat:
        st.success("未检测到问题。")


def proposals_and_queue_view(proposals: list[dict[str, Any]], queue: list[dict[str, Any]]) -> None:
    st.subheader("提案")
    ui.pretty_table(proposals) if proposals else st.info("尚未写入任何提案。")
    st.subheader("实验队列")
    ui.pretty_table(queue) if queue else st.info("尚未排队任何实验。")


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
        df = pd.DataFrame(points).set_index("date")[["value"]].rename(columns={"value": metric})
        st.caption(metric)
        st.line_chart(df, use_container_width=True)
