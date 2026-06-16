from __future__ import annotations

from pathlib import Path

import streamlit as st

from trading_agent.dashboard import charts, queries

st.set_page_config(page_title="Trading Agent — Read-Only Dashboard", layout="wide")

AGENT_ROOT = Path.cwd()

st.title("Trading Agent — Read-Only Dashboard")
st.caption(
    "Reads runtime/analytics/analytics.db and runtime/state/runs/* only. "
    "Does not write or modify any trading parameter."
)

run_dates = queries.list_run_dates(AGENT_ROOT)
if not run_dates:
    st.warning("No run dates found under runtime/state/runs/. Run the premarket pipeline first.")
    st.stop()

selected_run_date = st.selectbox("Run date", run_dates, index=0)

st.header("Overview")
charts.overview_metrics(queries.overview(AGENT_ROOT, selected_run_date))

st.header("Candidates")
charts.candidates_chart(queries.candidates_table(AGENT_ROOT, selected_run_date))

st.header("Decisions")
charts.decisions_timeline_table(queries.decisions_timeline(AGENT_ROOT, selected_run_date))

st.header("Orders")
charts.orders_table_view(queries.orders_table(AGENT_ROOT, selected_run_date))

st.header("Replay (fill rate + blocked reasons, across all run dates)")
charts.replay_summary_view(queries.replay_summary(AGENT_ROOT))

st.header("Self-Growth Lab (read-only diagnostics)")
charts.growth_observations_view(queries.growth_observations(AGENT_ROOT))
