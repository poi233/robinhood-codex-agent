from __future__ import annotations

from typing import Any

import streamlit as st


def overview_metrics(overview: dict[str, Any]) -> None:
    columns = st.columns(4)
    columns[0].metric("Plan state", overview.get("plan_state") or "-")
    columns[1].metric("Market regime", overview.get("market_regime") or "-")
    columns[2].metric("Watchlist / Tradable", f"{overview.get('watchlist_count', 0)} / {overview.get('tradable_count', 0)}")
    columns[3].metric("Top score", overview.get("top_score") if overview.get("top_score") is not None else "-")

    columns2 = st.columns(3)
    columns2[0].metric("Pending orders", overview.get("pending_order_count", 0))
    pnl = overview.get("today_pnl")
    columns2[1].metric("Realized PnL", f"${pnl:,.2f}" if pnl is not None else "-")
    equity = overview.get("total_equity")
    columns2[2].metric("Total equity", f"${equity:,.2f}" if equity is not None else "-")


def candidates_chart(rows: list[dict[str, Any]]) -> None:
    if not rows:
        st.info("No candidates for this run date.")
        return
    chart_data = {row["symbol"]: row.get("candidate_score") or 0 for row in rows}
    st.bar_chart(chart_data)
    st.dataframe(rows, use_container_width=True)


def decisions_timeline_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        st.info("No intraday decisions logged for this run date.")
        return
    st.dataframe(rows, use_container_width=True)


def orders_table_view(rows: list[dict[str, Any]]) -> None:
    if not rows:
        st.info("No paper orders for this run date.")
        return
    st.dataframe(rows, use_container_width=True)


def replay_summary_view(report: dict[str, Any]) -> None:
    if report.get("error"):
        st.warning("No replay data found yet. Run the premarket + intraday pipeline first.")
        return

    fill_rate = report.get("fill_rate") or {}
    blocked = report.get("blocked_reasons") or {}

    st.caption(f"Period: {report.get('run_date_count', 0)} run date(s)")
    columns = st.columns(4)
    columns[0].metric("Total orders", fill_rate.get("total_orders", 0))
    columns[1].metric("Fill rate", f"{fill_rate.get('fill_rate_pct', 0)}%")
    columns[2].metric("Evaluations", blocked.get("total_evaluations", 0))
    columns[3].metric("No-trade rate", f"{blocked.get('no_trade_rate_pct', 0)}%")

    reason_counts = blocked.get("reason_counts") or {}
    if reason_counts:
        st.subheader("Top blocked reasons")
        st.bar_chart(reason_counts)

    by_symbol = fill_rate.get("by_symbol") or {}
    if by_symbol:
        st.subheader("Fill rate by symbol")
        st.dataframe(
            [{"symbol": symbol, **counts} for symbol, counts in by_symbol.items()],
            use_container_width=True,
        )


def growth_observations_view(payload: dict) -> None:
    if not payload:
        st.info("No growth observations yet. Run: python3 -m trading_agent growth observe")
        return
    st.caption(f"generated_at: {payload.get('generated_at', '?')}  ·  run dates: {payload.get('run_date_count', 0)}")
    glob = payload.get("global") or []
    if glob:
        st.subheader("Global")
        st.dataframe(glob, use_container_width=True)
    modules = payload.get("modules") or {}
    flat = [{"module": m, **o} for m, obs in modules.items() for o in obs]
    if flat:
        st.subheader("By module")
        st.dataframe(flat, use_container_width=True)
    if not glob and not flat:
        st.success("No issues detected.")
