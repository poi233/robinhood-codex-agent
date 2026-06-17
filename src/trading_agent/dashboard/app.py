from __future__ import annotations

from pathlib import Path

import streamlit as st

from trading_agent.dashboard import charts, queries

st.set_page_config(page_title="Trading Agent — Read-Only Dashboard", layout="wide")


def _resolve_agent_root() -> Path:
    """Resolve the repository root from the installed module location.

    The dashboard is frequently launched from `src/` during local development, so
    relying on `Path.cwd()` would point at the wrong directory and hide valid run
    data under `repo_root/runtime/state/runs/`.
    """

    return Path(__file__).resolve().parents[3]


AGENT_ROOT = _resolve_agent_root()

st.title("Trading Agent — Read-Only Dashboard")
st.caption(
    "Reads runtime/analytics/analytics.db, runtime/state/runs/*, and growth artifacts only. "
    "Does not write or modify any trading parameter."
)

run_dates = queries.list_run_dates(AGENT_ROOT)
if not run_dates:
    st.warning("No run dates found under runtime/state/runs/. Run the premarket pipeline first.")
    st.stop()

with st.sidebar:
    st.header("Filters")
    selected_run_date = st.selectbox("Run date", run_dates, index=0)
    st.caption(f"{len(run_dates)} run date(s) available")
    st.caption("All views are read-only.")

today_tab, candidates_tab, decisions_tab, paper_tab, compare_tab, calibration_tab, growth_tab, themes_tab, trends_tab = st.tabs(
    ["① Today", "② Candidates", "③ Decisions", "④ Paper", "⑤ Strategy Comparison",
     "⑥ Calibration", "⑦ Self-Growth", "⑧ Themes", "⑨ Trends"]
)

with today_tab:
    st.header(f"Today — {selected_run_date}")
    charts.today_view(
        queries.overview(AGENT_ROOT, selected_run_date),
        queries.decisions_timeline(AGENT_ROOT, selected_run_date),
        queries.orders_table(AGENT_ROOT, selected_run_date),
    )

with candidates_tab:
    st.header("Candidates & Scores")
    charts.candidates_with_rankings_view(queries.candidates_with_rankings(AGENT_ROOT, selected_run_date))
    st.subheader("Price factors (H2 — factor_alpha)")
    charts.factor_view(queries.factor_alpha(AGENT_ROOT, selected_run_date))

with decisions_tab:
    st.header("Decisions & Blocked Reasons")
    charts.decisions_timeline_table(queries.decisions_timeline(AGENT_ROOT, selected_run_date))
    st.subheader("Blocked-reason trend (all run dates)")
    charts.blocked_reason_trend_view(queries.blocked_reason_trend(AGENT_ROOT))
    st.subheader("Fill rate + blocked reasons (across all run dates)")
    charts.replay_summary_view(queries.replay_summary(AGENT_ROOT))

with paper_tab:
    st.header("Paper Performance")
    charts.equity_curve_view(queries.equity_timeseries(AGENT_ROOT))
    st.subheader("Orders (selected run date)")
    charts.orders_table_view(queries.orders_table(AGENT_ROOT, selected_run_date))

with compare_tab:
    st.header("Strategy Comparison")
    charts.strategy_comparison_view(queries.strategy_comparison(AGENT_ROOT))
    charts.champion_vs_challengers_view(queries.champion_vs_challengers(AGENT_ROOT))

with calibration_tab:
    st.header("Calibration (E1: which scores / setups actually work)")
    charts.calibration_view(queries.calibration_report(AGENT_ROOT))
    st.divider()
    st.subheader("Fill quality (E4: how optimistic are paper fills?)")
    charts.fill_quality_view(queries.fill_quality_report(AGENT_ROOT))
    st.divider()
    st.subheader("AI signal study (H3: confidence calibration + directional accuracy)")
    charts.ai_signal_study_view(queries.ai_signal_study(AGENT_ROOT))
    st.divider()
    st.subheader("AI layer ablation (H3: each layer's marginal IC)")
    charts.ai_ablation_view(queries.ai_ablation(AGENT_ROOT))

with growth_tab:
    st.header("Self-Growth Lab (read-only)")
    charts.growth_observations_view(queries.growth_observations(AGENT_ROOT))
    charts.proposals_and_queue_view(
        queries.proposals_overview(AGENT_ROOT),
        queries.experiment_queue_overview(AGENT_ROOT),
    )

with themes_tab:
    st.header("Themes & Exposure")
    charts.theme_diagnostics_view(queries.theme_diagnostics(AGENT_ROOT, selected_run_date))

with trends_tab:
    st.header("Trends (I: nightly analysis snapshots over time)")
    _history_dates = queries.analysis_history_dates(AGENT_ROOT)
    _selected_snapshot_date = st.selectbox("Analysis snapshot date", _history_dates) if _history_dates else None
    charts.trends_view(
        _history_dates,
        queries.analysis_snapshot(AGENT_ROOT, _selected_snapshot_date) if _selected_snapshot_date else {},
        queries.analysis_trend(AGENT_ROOT),
    )
