from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from trading_agent.dashboard import charts, queries, ui

st.set_page_config(page_title="交易代理 · 只读看板", layout="wide", page_icon="📈")


def _resolve_agent_root() -> Path:
    """Resolve the repo root that holds runtime/ data.

    Honors the ``AGENT_ROOT`` env var first (same knob launchd/cron use, see
    ``core.context.resolve_agent_root``); otherwise derives the root from the
    installed module location. ``cwd`` is intentionally ignored: the dashboard is
    frequently launched from ``src/`` and relying on it would hide valid run data
    under ``repo_root/runtime/state/runs/``.
    """

    env_root = os.environ.get("AGENT_ROOT")
    if env_root:
        candidate = Path(env_root).expanduser().resolve()
        if candidate.exists():
            return candidate
    return Path(__file__).resolve().parents[3]


AGENT_ROOT = _resolve_agent_root()

ui.inject_theme()

st.title("📈 交易代理 · 只读看板")
st.caption(
    "仅读取 runtime/analytics/analytics.db、runtime/state/runs/* 与成长产物；"
    "不写入、不修改任何交易参数。"
)

run_dates = queries.list_run_dates(AGENT_ROOT)
if not run_dates:
    st.warning("在 runtime/state/runs/ 下未找到运行日。请先跑 premarket 流程。")
    st.stop()

with st.sidebar:
    st.header("筛选")
    selected_run_date = st.selectbox("运行日", run_dates, index=0)
    st.caption(f"共 {len(run_dates)} 个运行日")
    st.caption("所有视图均为只读。")

cockpit_tab, picks_tab, perf_tab, calib_tab, growth_tab = st.tabs(
    ["📊 今日驾驶舱", "🎯 选股与决策", "💰 业绩与对比", "🔬 校准与归因", "🌱 成长与趋势"]
)

# ── 📊 今日驾驶舱 ──────────────────────────────────────────
with cockpit_tab:
    st.header(f"今日驾驶舱 — {selected_run_date}")
    ui.guidance_box(
        what="今天系统的整体状态：能不能交易、市场处于什么状态、账户权益与盈亏。",
        how="先看两条横幅（市场状态 / 夜间健康）是否正常，再看 KPI 卡片的颜色与「vs 上一交易日」箭头。",
        action="计划状态非 trade_ready 或出现红色横幅时，今天以观察为主；权益/盈亏走弱要回到「选股与决策」查原因。",
    )
    charts.regime_banner(queries.regime_state(AGENT_ROOT, selected_run_date))
    charts.nightly_health_banner(queries.nightly_health(AGENT_ROOT))
    charts.kpi_overview(queries.overview_with_delta(AGENT_ROOT, selected_run_date))

    charts.today_decision(queries.decisions_timeline(AGENT_ROOT, selected_run_date))

    st.subheader("组合集中度（K1 · advisory）")
    charts.portfolio_target_view(queries.portfolio_target(AGENT_ROOT, selected_run_date))

    st.subheader("今日订单")
    charts.orders_table_view(queries.orders_table(AGENT_ROOT, selected_run_date))

# ── 🎯 选股与决策 ──────────────────────────────────────────
with picks_tab:
    st.header(f"选股与决策 — {selected_run_date}")
    ui.guidance_box(
        what="候选股从综合评分 → 价量因子 → 叠加 → 最终决策的完整链路，以及为什么被拦截。",
        how="评分越高排越前；因子α分给出独立的价量视角；叠加表显示各信号如何微调最终排名。",
        action="若高分股频繁被同一原因拦截，到「校准与归因」核对该门槛是否过严。",
    )
    st.subheader("候选与评分")
    charts.candidates_with_rankings_view(queries.candidates_with_rankings(AGENT_ROOT, selected_run_date))

    st.subheader("价量因子（factor_alpha）")
    charts.factor_view(queries.factor_alpha(AGENT_ROOT, selected_run_date))

    st.subheader("决策叠加（各信号如何影响最终决策）")
    charts.advisory_overlay_view(queries.advisory_overlay_summary(AGENT_ROOT, selected_run_date))

    st.subheader("决策时间线")
    charts.decisions_timeline_table(queries.decisions_timeline(AGENT_ROOT, selected_run_date))

    st.subheader("拦截原因趋势（所有运行日）")
    charts.blocked_reason_trend_view(queries.blocked_reason_trend(AGENT_ROOT))

    st.subheader("成交率 + 拦截原因（跨所有运行日）")
    charts.replay_summary_view(queries.replay_summary(AGENT_ROOT))

# ── 💰 业绩与对比 ──────────────────────────────────────────
with perf_tab:
    st.header("业绩与对比")
    ui.guidance_box(
        what="纸面账户权益曲线（叠加 SPY 大盘基准）与不同策略版本的横向对比。",
        how="超额收益 (alpha) 为正即跑赢大盘；策略对比表中 ⭐ 标记累计盈亏最高的版本。",
        action="持续跑输大盘要回到校准查信号有效性；切换策略版本前先看影子挑战者是否「建议升级」。",
    )
    st.subheader("权益曲线 vs 大盘基准")
    charts.equity_curve_view(queries.equity_with_benchmark(AGENT_ROOT))

    charts.strategy_comparison_view(queries.strategy_comparison(AGENT_ROOT))
    charts.champion_vs_challengers_view(queries.champion_vs_challengers(AGENT_ROOT))

    st.subheader(f"订单（运行日 {selected_run_date}）")
    charts.orders_table_view(queries.orders_table(AGENT_ROOT, selected_run_date))

# ── 🔬 校准与归因 ──────────────────────────────────────────
with calib_tab:
    st.header("校准与归因")
    ui.guidance_box(
        what="用历史远期收益检验：评分/信号到底灵不灵、哪类投资逻辑与主题真正赚钱。",
        how="评分分桶应单调（分越高收益越高）；IC 的 |t|≥2 才算信号真实；胜率红绿排序看哪类逻辑占优。",
        action="只在 15–30 个运行日后才据此调权重；采纳建议须走 shadow 验证 + 人工 promote，绝不直接改 champion。",
    )
    st.subheader("评分校准（哪些分数 / 形态真有效）")
    charts.calibration_view(queries.calibration_report(AGENT_ROOT))
    st.divider()
    st.subheader("成交质量（纸面成交有多乐观）")
    charts.fill_quality_view(queries.fill_quality_report(AGENT_ROOT))
    st.divider()
    st.subheader("AI 信号研究（置信度校准 + 方向准确率）")
    charts.ai_signal_study_view(queries.ai_signal_study(AGENT_ROOT))
    st.divider()
    st.subheader("AI 分层消融（每层的边际 IC）")
    charts.ai_ablation_view(queries.ai_ablation(AGENT_ROOT))
    st.divider()
    st.subheader("投资逻辑归因（哪类逻辑真赚钱）")
    charts.thesis_attribution_view(queries.thesis_attribution(AGENT_ROOT))
    st.subheader("各逻辑胜率趋势（按夜间快照）")
    charts.thesis_trend_view(queries.thesis_trend(AGENT_ROOT))
    st.divider()
    st.subheader("主题敞口诊断")
    charts.theme_diagnostics_view(queries.theme_diagnostics(AGENT_ROOT, selected_run_date))

# ── 🌱 成长与趋势 ──────────────────────────────────────────
with growth_tab:
    st.header("成长与趋势")
    ui.guidance_box(
        what="自成长实验室（只读）的诊断 / 提案 / 实验队列，以及各指标随时间的走向。",
        how="成长观测给出系统自检问题；趋势线看成交率 / 空仓率 / 样本量是否朝好的方向移动。",
        action="提案只是草稿，绝不自动启用；趋势恶化时回到对应主区定位根因。",
    )
    st.subheader("自成长实验室（只读）")
    charts.growth_observations_view(queries.growth_observations(AGENT_ROOT))
    charts.proposals_and_queue_view(
        queries.proposals_overview(AGENT_ROOT),
        queries.experiment_queue_overview(AGENT_ROOT),
    )
    st.divider()
    st.subheader("趋势（夜间分析快照随时间）")
    _history_dates = queries.analysis_history_dates(AGENT_ROOT)
    _selected_snapshot_date = st.selectbox("分析快照日期", _history_dates) if _history_dates else None
    charts.trends_view(
        _history_dates,
        queries.analysis_snapshot(AGENT_ROOT, _selected_snapshot_date) if _selected_snapshot_date else {},
        queries.analysis_trend(AGENT_ROOT),
    )
