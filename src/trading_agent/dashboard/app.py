from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from trading_agent.dashboard import charts, queries, ui

st.set_page_config(page_title="交易代理 · 只读看板", layout="wide")


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

ui.app_title("交易代理看板", "只读 · runtime/state + analytics")

PAGE_BRIEFS = {
    "cockpit": ui.PageBrief(
        "今日驾驶舱",
        "市场状态 · 执行结论 · 数据完整度",
        "今天系统的整体状态：能不能交易、市场处于什么状态、账户权益与盈亏。",
        "先看状态横幅和 KPI 卡片；明细默认折叠。",
        "计划状态非 trade_ready 或出现红色横幅时，以观察为主。",
        dated=True,
    ),
    "picks": ui.PageBrief(
        "选股与决策",
        "Top 候选 · 成交/空仓 · 拦截原因",
        "候选股、评分、因子和拦截原因的主链路。",
        "先看 Top 候选和成交/空仓摘要；研究明细默认折叠。",
        "高分股反复被同一原因拦截时，再展开明细定位门槛。",
        dated=True,
    ),
    "performance": ui.PageBrief(
        "业绩与对比",
        "纸面权益 · 基准 · 策略版本",
        "纸面账户权益曲线、SPY 基准和策略版本对比。",
        "先看收益/alpha 卡片，再展开策略细节。",
        "持续跑输大盘时回到校准查信号有效性。",
    ),
    "kline": ui.PageBrief(
        "K线复盘",
        "日 K · 均线 · 买卖点",
        "单标的日 K 与买卖点。",
        "默认只看图；策略行为表默认折叠。",
        "用来复盘入场区、追高拦截和实际成交位置。",
    ),
    "calibration": ui.PageBrief(
        "校准与归因",
        "样本 · IC · 归因",
        "用历史远期收益检验评分和信号是否有效。",
        "先看样本数和统计状态；细节默认折叠。",
        "样本少时只看方向，不直接调权重。",
    ),
    "growth": ui.PageBrief(
        "成长与趋势",
        "观测 · 提案 · 快照",
        "自成长实验室的诊断、提案、实验队列和趋势。",
        "默认只看问题摘要，提案和趋势放在详情里。",
        "提案只是草稿，必须 shadow 验证后再人工 promote。",
    ),
}

run_dates = queries.list_run_dates(AGENT_ROOT)
if not run_dates:
    st.warning("在 runtime/state/runs/ 下未找到运行日。请先跑 premarket 流程。")
    st.stop()

with st.sidebar:
    st.header("筛选")
    selected_run_date = st.selectbox("运行日", run_dates, index=0)
    st.caption(f"共 {len(run_dates)} 个运行日")
    show_help = st.toggle("显示说明", value=False)
    show_detail = st.toggle("展开研究明细", value=False)
    st.caption("只读。默认显示关键摘要。")

active_page = st.segmented_control(
    "页面",
    ["总览", "选股", "业绩", "日线", "校准", "成长"],
    default="总览",
    key="dashboard_page",
    label_visibility="collapsed",
)

# ── 今日驾驶舱 ──────────────────────────────────────────
if active_page == "总览":
    ui.page_header(PAGE_BRIEFS["cockpit"], run_date=selected_run_date, show_help=show_help)
    _overview_delta = queries.overview_with_delta(AGENT_ROOT, selected_run_date)
    _completeness = queries.data_completeness(AGENT_ROOT, selected_run_date)
    _regime = queries.regime_state(AGENT_ROOT, selected_run_date)
    _decisions = queries.decisions_timeline(AGENT_ROOT, selected_run_date)
    charts.cockpit_hero(_overview_delta, _completeness, _regime, _decisions)

    ui.section_band("最新决策", "盘中执行层")
    charts.today_decision(_decisions)

    with ui.detail_expander("运行指标与数据完整度", show_detail=show_detail):
        charts.kpi_overview(_overview_delta)
        charts.data_completeness_view(_completeness)

    with ui.detail_expander("组合与订单", show_detail=show_detail):
        st.subheader("组合集中度")
        charts.portfolio_target_view(queries.portfolio_target(AGENT_ROOT, selected_run_date))
        st.subheader("今日订单")
        charts.orders_table_view(queries.orders_table(AGENT_ROOT, selected_run_date))

# ── 选股与决策 ──────────────────────────────────────────
elif active_page == "选股":
    ui.page_header(PAGE_BRIEFS["picks"], run_date=selected_run_date, show_help=show_help)
    charts.candidates_with_rankings_view(queries.candidates_with_rankings(AGENT_ROOT, selected_run_date))

    st.subheader("每周选股（O1）")
    charts.screener_change_view(queries.screener_change(AGENT_ROOT))
    st.subheader("今日 active 选择（O2）")
    charts.active_selection_view(queries.active_selection(AGENT_ROOT, selected_run_date))

    charts.replay_summary_view(queries.replay_summary(AGENT_ROOT))

    with ui.detail_expander("因子、叠加与决策明细", show_detail=show_detail):
        st.subheader("价量因子")
        charts.factor_view(queries.factor_alpha(AGENT_ROOT, selected_run_date))

        st.subheader("基本面与事件（H7/H8）")
        charts.fundamental_event_view(queries.fundamental_event(AGENT_ROOT, selected_run_date))

        st.subheader("决策叠加")
        charts.advisory_overlay_view(queries.advisory_overlay_summary(AGENT_ROOT, selected_run_date))

        st.subheader("决策时间线")
        charts.decisions_timeline_table(queries.decisions_timeline(AGENT_ROOT, selected_run_date))

        st.subheader("拦截原因趋势")
        charts.blocked_reason_trend_view(queries.blocked_reason_trend(AGENT_ROOT))

# ── 业绩与对比 ──────────────────────────────────────────
elif active_page == "业绩":
    ui.page_header(PAGE_BRIEFS["performance"], show_help=show_help)
    charts.equity_curve_view(queries.equity_with_benchmark(AGENT_ROOT))

    with ui.detail_expander("策略版本与影子实验", show_detail=show_detail):
        charts.strategy_comparison_view(queries.strategy_comparison(AGENT_ROOT))
        charts.champion_vs_challengers_view(queries.champion_vs_challengers(AGENT_ROOT))
        st.subheader("策略权益重放")
        charts.strategy_equity_replay_view(queries.strategy_equity_curves(AGENT_ROOT))
        st.subheader(f"策略行为对比 — {selected_run_date}")
        charts.strategy_behavior_view(queries.strategy_behavior(AGENT_ROOT, selected_run_date))

    with ui.detail_expander("订单明细"):
        charts.orders_table_view(queries.orders_table(AGENT_ROOT, selected_run_date))

# ── K线复盘 ─────────────────────────────────────────────
elif active_page == "日线":
    ui.page_header(PAGE_BRIEFS["kline"], show_help=show_help)
    _kline_symbols = queries.available_kline_symbols(AGENT_ROOT)
    if not _kline_symbols:
        st.info("暂无本地日线数据（market_feed 在 premarket 采集 OHLCV 后生成）。先跑 premarket 流程。")
    else:
        _sym = st.selectbox("选择标的", _kline_symbols, index=0)
        _trades = queries.trades_for_symbol(AGENT_ROOT, _sym)
        _strats = list(_trades.keys())
        _picked = st.multiselect(
            "叠加的策略（默认全部）", _strats, default=_strats,
            help="champion = 实际纸面账本；其余为各挑战者隔离账本（experiments/<id>）。",
        ) if _strats else []
        _ohlcv = queries.ohlcv_daily(AGENT_ROOT, _sym)
        ui.metric_row([
            ui.MetricCard("可复盘标的", str(len(_kline_symbols))),
            ui.MetricCard("当前标的", _sym),
            ui.MetricCard("叠加策略", str(len(_picked)) if _strats else "0"),
            ui.MetricCard("日线根数", str(len(_ohlcv))),
        ])
        charts.kline_view(_sym, _ohlcv, _trades, selected_strategies=_picked if _strats else None)
        with ui.detail_expander("该标的决策行为", show_detail=show_detail):
            charts.symbol_behavior_view(queries.decisions_for_symbol(AGENT_ROOT, _sym))

# ── 校准与归因 ──────────────────────────────────────────
elif active_page == "校准":
    ui.page_header(PAGE_BRIEFS["calibration"], show_help=show_help)
    charts.calibration_view(queries.calibration_report(AGENT_ROOT))
    st.subheader("选股有效性（O4）")
    charts.screen_eval_view(queries.screen_eval_report(AGENT_ROOT))
    with ui.detail_expander("成交、AI、逻辑和主题细节", show_detail=show_detail):
        st.subheader("成交质量")
        charts.fill_quality_view(queries.fill_quality_report(AGENT_ROOT))
        st.subheader("AI 信号研究")
        charts.ai_signal_study_view(queries.ai_signal_study(AGENT_ROOT))
        st.subheader("AI 分层消融")
        charts.ai_ablation_view(queries.ai_ablation(AGENT_ROOT))
        st.subheader("投资逻辑归因")
        charts.thesis_attribution_view(queries.thesis_attribution(AGENT_ROOT))
        st.subheader("各逻辑胜率趋势")
        charts.thesis_trend_view(queries.thesis_trend(AGENT_ROOT))
        st.subheader("主题敞口诊断")
        charts.theme_diagnostics_view(queries.theme_diagnostics(AGENT_ROOT, selected_run_date))

# ── 成长与趋势 ──────────────────────────────────────────
elif active_page == "成长":
    ui.page_header(PAGE_BRIEFS["growth"], show_help=show_help)
    charts.growth_observations_view(queries.growth_observations(AGENT_ROOT))
    with ui.detail_expander("提案、实验队列与趋势", show_detail=show_detail):
        charts.proposals_and_queue_view(
            queries.proposals_overview(AGENT_ROOT),
            queries.experiment_queue_overview(AGENT_ROOT),
        )
        st.subheader("趋势")
        _history_dates = queries.analysis_history_dates(AGENT_ROOT)
        _selected_snapshot_date = st.selectbox("分析快照日期", _history_dates) if _history_dates else None
        charts.trends_view(
            _history_dates,
            queries.analysis_snapshot(AGENT_ROOT, _selected_snapshot_date) if _selected_snapshot_date else {},
            queries.analysis_trend(AGENT_ROOT),
        )
