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


# --- C3 Dashboard v2 components (read-only) ---

_PLAN_STATE_ICON = {"trade_ready": "🟢", "observe_only": "🟡", "no_trade": "🔴", "normal": "🟢"}


def plan_state_badge(plan_state: str | None) -> str:
    icon = _PLAN_STATE_ICON.get(str(plan_state or "").lower(), "⚪️")
    return f"{icon} {plan_state or '-'}"


def today_view(overview: dict[str, Any], decisions: list[dict[str, Any]], orders: list[dict[str, Any]]) -> None:
    columns = st.columns(4)
    columns[0].metric("Plan state", plan_state_badge(overview.get("plan_state")))
    columns[1].metric("Market regime", overview.get("market_regime") or "-")
    columns[2].metric("Watchlist / Tradable", f"{overview.get('watchlist_count', 0)} / {overview.get('tradable_count', 0)}")
    pnl = overview.get("today_pnl")
    columns[3].metric("Realized PnL", f"${pnl:,.2f}" if pnl is not None else "-")

    st.subheader("Today's decision — why we did / didn't trade")
    if not decisions:
        st.info("No intraday decision logged yet for this run date.")
    else:
        latest = decisions[-1]
        verdict = str(latest.get("decision") or "-")
        if verdict == "would_trade":
            st.success(f"**would_trade** — {latest.get('symbol') or ''} {latest.get('side') or ''} "
                       f"({latest.get('setup_type') or ''})")
        else:
            reasons = latest.get("blocked_reasons")
            try:
                reasons = ", ".join(__import__("json").loads(reasons)) if isinstance(reasons, str) else ", ".join(reasons or [])
            except Exception:
                pass
            st.warning(f"**{verdict}** — blocked by: {reasons or 'n/a'}")
        st.dataframe(decisions, use_container_width=True)

    st.subheader("Orders")
    st.dataframe(orders, use_container_width=True) if orders else st.info("No paper orders for this run date.")


def candidates_with_rankings_view(rows: list[dict[str, Any]]) -> None:
    if not rows:
        st.info("No scored candidates for this run date.")
        return
    st.bar_chart({row["symbol"]: row.get("candidate_score") or 0 for row in rows})
    st.dataframe(rows, use_container_width=True)


def equity_curve_view(series: list[dict[str, Any]]) -> None:
    if not series:
        st.info("No paper equity history yet.")
        return
    equity = {row["timestamp"]: row.get("total_equity") for row in series if row.get("total_equity") is not None}
    pnl = {row["timestamp"]: row.get("realized_pnl") for row in series if row.get("realized_pnl") is not None}
    if equity:
        st.subheader("Total equity")
        st.line_chart(equity)
    if pnl:
        st.subheader("Realized PnL")
        st.line_chart(pnl)


def blocked_reason_trend_view(trend: list[dict[str, Any]]) -> None:
    if not trend:
        st.info("No blocked-reason history yet.")
        return
    st.dataframe(trend, use_container_width=True)


def strategy_comparison_view(rows: list[dict[str, Any]]) -> None:
    st.subheader("Champion versions (by strategy_id)")
    if not rows:
        st.info("No strategy versions with runs yet. This fills in once ≥1 run is tagged with a strategy_id "
                "(and becomes a real comparison after you switch to a second strategy version).")
        return
    if len(rows) == 1:
        st.caption("Only one strategy version so far — side-by-side comparison appears after a second version accrues runs.")
    st.dataframe(rows, use_container_width=True)
    st.bar_chart({row["strategy_id"]: row.get("fill_rate_pct") or 0 for row in rows})


def champion_vs_challengers_view(report: dict[str, Any]) -> None:
    st.subheader("Champion vs shadow challengers")
    if not report or not report.get("challengers"):
        st.info("No shadow experiments evaluated yet. Run: python3 -m trading_agent growth evaluate")
        return
    champion = report.get("champion") or {}
    columns = st.columns(3)
    columns[0].metric("Champion fill rate", f"{champion.get('fill_rate_pct', 0)}%")
    columns[1].metric("Champion no-trade rate", f"{champion.get('no_trade_rate_pct', 0)}%")
    columns[2].metric("Champion trading days", champion.get("run_date_count", 0))
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
            "blocking_reasons": "; ".join(rec.get("blocking_reasons") or []),
        })
    st.dataframe(flat, use_container_width=True)


def proposals_and_queue_view(proposals: list[dict[str, Any]], queue: list[dict[str, Any]]) -> None:
    st.subheader("Proposals")
    st.dataframe(proposals, use_container_width=True) if proposals else st.info("No proposals written yet.")
    st.subheader("Experiment queue")
    st.dataframe(queue, use_container_width=True) if queue else st.info("No experiments queued yet.")


def theme_diagnostics_view(diagnostics: dict[str, Any]) -> None:
    if not diagnostics:
        st.info("No theme diagnostics for this run date.")
        return
    for bucket, payload in diagnostics.items():
        if not isinstance(payload, dict):
            continue
        st.subheader(f"{bucket}")
        distribution = payload.get("theme_distribution")
        if isinstance(distribution, dict) and distribution:
            st.bar_chart({theme: (info.get("pct") if isinstance(info, dict) else info) for theme, info in distribution.items()})
        st.json({k: v for k, v in payload.items() if k != "theme_distribution"})


def calibration_view(report: dict) -> None:
    if not report or not report.get("sample_size"):
        st.info("No calibration data yet. Run: python3 -m trading_agent analytics calibrate "
                "(needs network for yfinance; meaningful after ~15+ run dates).")
        return
    st.caption(f"generated_at: {report.get('generated_at', '?')}  ·  run dates: {report.get('run_date_count', 0)}  "
               f"·  samples: {report.get('sample_size', 0)}  ·  horizons(d): {report.get('horizons')}")
    st.warning("Small samples are noisy — trust bucket monotonicity / IC only after 15–30 run dates.")

    st.subheader("Score buckets vs forward return")
    for field, per_h in (report.get("score_buckets") or {}).items():
        for horizon, buckets in per_h.items():
            if not buckets:
                continue
            st.markdown(f"**{field} · {horizon}d** (does higher score → higher return?)")
            st.dataframe(buckets, use_container_width=True)
            st.bar_chart({f"b{b['bucket']}": b["mean_return"] for b in buckets})

    st.subheader("Component attribution (Spearman IC, ranked)")
    for horizon, rows in (report.get("attribution") or {}).items():
        st.markdown(f"**{horizon}d**")
        st.dataframe(rows, use_container_width=True)

    st.subheader("Benchmark returns (alpha vs beta)")
    bench_rows = [{"benchmark": sym, **{f"{h}d": v.get("mean_return") for h, v in per.items()}}
                  for sym, per in (report.get("benchmarks") or {}).items()]
    if bench_rows:
        st.dataframe(bench_rows, use_container_width=True)

    st.subheader("Setup outcomes (target_1 before stop)")
    if report.get("setup_outcomes"):
        st.dataframe(report["setup_outcomes"], use_container_width=True)
