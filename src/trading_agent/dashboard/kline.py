"""K线复盘 (candlestick review) — professional figure builder. Read-only / presentation only.

Interactive Plotly chart styled like a pro trading terminal:
  • Price panel: candlesticks + SMA20/50/200 + Bollinger(20,2) band + last-price line.
  • Per-strategy buy(▲)/sell(▼) markers, each strategy its own color.
  • Trade-plan overlays: each buy's stop (red) / target_1·target_2 (green) levels, the
    holding period shaded, and a buy→sell connector colored by round-trip P&L.
  • Volume panel (+ volume MA20), RSI(14) panel (70/30 guides), MACD(12/26/9) panel.
  • Date axis with weekend rangebreaks, range-selector buttons, crosshair spikes, right y-axis.

Plotly is an optional ``[dashboard]`` extra; the caller guards the import.
"""
from __future__ import annotations

from typing import Any

import plotly.graph_objects as go
from plotly.subplots import make_subplots

GOOD = "#16c784"
BAD = "#ea3943"
TEXT = "#e6edf6"
GRID = "rgba(255,255,255,0.06)"
BG = "#0e1117"
PANEL = "#0e1117"
SMA_COLORS = {20: "#f0a500", 50: "#a855f7", 200: "#38bdf8"}
BB_FILL = "rgba(56,189,248,0.06)"
STRATEGY_COLORS = ["#3b82f6", "#06b6d4", "#ec4899", "#84cc16", "#f97316", "#a855f7"]


# ---- pure-python indicators ----

def _sma(values: list[float], window: int) -> list[float | None]:
    out: list[float | None] = []
    run = 0.0
    for i, v in enumerate(values):
        run += v
        if i >= window:
            run -= values[i - window]
        out.append(round(run / window, 4) if i >= window - 1 else None)
    return out


def _rolling_std(values: list[float], window: int) -> list[float | None]:
    out: list[float | None] = []
    for i in range(len(values)):
        if i < window - 1:
            out.append(None)
            continue
        win = values[i - window + 1:i + 1]
        mean = sum(win) / window
        var = sum((x - mean) ** 2 for x in win) / window
        out.append(var ** 0.5)
    return out


def _ema(values: list[float], window: int) -> list[float]:
    if not values:
        return []
    k = 2 / (window + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def _macd(closes: list[float]) -> tuple[list[float], list[float], list[float]]:
    if len(closes) < 2:
        z = [0.0] * len(closes)
        return z, z, z
    macd = [a - b for a, b in zip(_ema(closes, 12), _ema(closes, 26))]
    signal = _ema(macd, 9)
    return macd, signal, [m - s for m, s in zip(macd, signal)]


def _rsi(closes: list[float], window: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    if len(closes) <= window:
        return out
    gains = [max(closes[i] - closes[i - 1], 0) for i in range(1, len(closes))]
    losses = [max(closes[i - 1] - closes[i], 0) for i in range(1, len(closes))]
    avg_g = sum(gains[:window]) / window
    avg_l = sum(losses[:window]) / window
    for i in range(window, len(closes)):
        if i > window:
            avg_g = (avg_g * (window - 1) + gains[i - 1]) / window
            avg_l = (avg_l * (window - 1) + losses[i - 1]) / window
        rs = avg_g / avg_l if avg_l else float("inf")
        out[i] = round(100 - 100 / (1 + rs), 2)
    return out


def summarize_strategy_trades(trades: list[dict[str, Any]], last_close: float | None) -> dict[str, Any]:
    """FIFO-match buys↔sells into round trips; return trade stats for one strategy.

    Returns realized P&L / win rate / avg R / avg hold-days over closed round trips, plus any
    still-open lots marked-to-market at ``last_close``. Pure; never raises on missing fields.
    """
    ordered = sorted(trades, key=lambda t: str(t.get("timestamp") or t.get("date") or ""))
    open_lots: list[dict[str, Any]] = []
    round_trips: list[dict[str, Any]] = []
    for t in ordered:
        price = t.get("price")
        qty = t.get("quantity") or 0
        if price is None:
            continue
        if t.get("side") == "buy":
            open_lots.append({"price": float(price), "qty": float(qty), "date": t.get("date"),
                              "stop": t.get("stop_price")})
        elif t.get("side") == "sell":
            remaining = float(qty)
            while remaining > 1e-9 and open_lots:
                lot = open_lots[0]
                matched = min(remaining, lot["qty"])
                pnl = (float(price) - lot["price"]) * matched
                risk = (lot["price"] - float(lot["stop"])) if lot.get("stop") else None
                r_mult = ((float(price) - lot["price"]) / risk) if risk and risk > 0 else None
                round_trips.append({"buy_date": lot["date"], "sell_date": t.get("date"),
                                    "buy_price": lot["price"], "sell_price": float(price),
                                    "qty": matched, "pnl": pnl, "r_mult": r_mult})
                lot["qty"] -= matched
                remaining -= matched
                if lot["qty"] <= 1e-9:
                    open_lots.pop(0)
    realized = sum(rt["pnl"] for rt in round_trips)
    wins = sum(1 for rt in round_trips if rt["pnl"] > 0)
    r_vals = [rt["r_mult"] for rt in round_trips if rt["r_mult"] is not None]
    open_qty = sum(l["qty"] for l in open_lots)
    avg_open = (sum(l["price"] * l["qty"] for l in open_lots) / open_qty) if open_qty else None
    unrealized = ((last_close - avg_open) * open_qty) if (avg_open is not None and last_close is not None) else None
    return {
        "trades": len(trades),
        "round_trips": len(round_trips),
        "win_rate": round(wins / len(round_trips) * 100, 1) if round_trips else None,
        "realized_pnl": round(realized, 2) if round_trips else None,
        "avg_r": round(sum(r_vals) / len(r_vals), 2) if r_vals else None,
        "open_qty": round(open_qty, 4),
        "avg_open_price": round(avg_open, 2) if avg_open is not None else None,
        "unrealized_pnl": round(unrealized, 2) if unrealized is not None else None,
        "_round_trips": round_trips,
    }


def build_kline_figure(
    symbol: str,
    ohlcv: list[dict[str, Any]],
    trades_by_strategy: dict[str, list[dict[str, Any]]],
    *,
    selected_strategies: list[str] | None = None,
    show_bbands: bool = True,
) -> go.Figure:
    dates = [str(r.get("timestamp") or "")[:10] for r in ohlcv]
    opens = [float(r.get("open") or 0) for r in ohlcv]
    highs = [float(r.get("high") or 0) for r in ohlcv]
    lows = [float(r.get("low") or 0) for r in ohlcv]
    closes = [float(r.get("close") or 0) for r in ohlcv]
    volumes = [float(r.get("volume") or 0) for r in ohlcv]
    last_close = closes[-1] if closes else None
    date_idx = {dt: i for i, dt in enumerate(dates)}

    fig = make_subplots(
        rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.025,
        row_heights=[0.56, 0.13, 0.13, 0.18],
        subplot_titles=(f"{symbol} 日K · SMA20/50/200 · 布林(20,2) · 买卖点与交易计划",
                        "成交量", "RSI(14)", "MACD(12/26/9)"),
    )

    # --- price panel ---
    fig.add_trace(go.Candlestick(
        x=dates, open=opens, high=highs, low=lows, close=closes, name="K线",
        increasing_line_color=GOOD, decreasing_line_color=BAD,
        increasing_fillcolor=GOOD, decreasing_fillcolor=BAD, legendgroup="px"), row=1, col=1)

    if show_bbands:
        mid = _sma(closes, 20)
        sd = _rolling_std(closes, 20)
        upper = [m + 2 * s if (m is not None and s is not None) else None for m, s in zip(mid, sd)]
        lower = [m - 2 * s if (m is not None and s is not None) else None for m, s in zip(mid, sd)]
        fig.add_trace(go.Scatter(x=dates, y=upper, name="布林上轨", mode="lines",
                                 line=dict(color="rgba(56,189,248,0.5)", width=1), legendgroup="bb",
                                 showlegend=False), row=1, col=1)
        fig.add_trace(go.Scatter(x=dates, y=lower, name="布林(20,2)", mode="lines",
                                 line=dict(color="rgba(56,189,248,0.5)", width=1), fill="tonexty",
                                 fillcolor=BB_FILL, legendgroup="bb"), row=1, col=1)
    for window, color in SMA_COLORS.items():
        fig.add_trace(go.Scatter(x=dates, y=_sma(closes, window), name=f"SMA{window}", mode="lines",
                                 line=dict(color=color, width=1.3), connectgaps=False), row=1, col=1)

    if last_close is not None:
        fig.add_hline(y=last_close, line=dict(color="rgba(230,237,246,0.35)", width=1, dash="dot"),
                      row=1, col=1, annotation_text=f"现价 {last_close:g}",
                      annotation_position="right", annotation_font_color=TEXT)

    # --- per-strategy trades: markers + trade-plan levels + round-trip connectors + holding shade ---
    strategies = selected_strategies if selected_strategies is not None else list(trades_by_strategy.keys())
    price_span = (max(highs) - min(lows)) if highs and lows else 1.0
    for idx, strat in enumerate(strategies):
        trades = trades_by_strategy.get(strat) or []
        if not trades:
            continue
        color = STRATEGY_COLORS[idx % len(STRATEGY_COLORS)]
        for side, sym_marker, dy in (("buy", "triangle-up", -1), ("sell", "triangle-down", 1)):
            pts = [t for t in trades if t.get("side") == side and t.get("price") is not None]
            if not pts:
                continue
            fig.add_trace(go.Scatter(
                x=[t["date"] for t in pts],
                y=[float(t["price"]) + dy * price_span * 0.02 for t in pts],
                name=f"{strat} · {'买' if side == 'buy' else '卖'}", mode="markers",
                marker=dict(symbol=sym_marker, size=13, color=color, line=dict(width=1, color=BG)),
                legendgroup=strat,
                customdata=[[t.get("quantity"), t.get("setup_type") or "—", t.get("price"),
                             t.get("stop_price") if t.get("stop_price") is not None else "—",
                             t.get("target_1") if t.get("target_1") is not None else "—",
                             t.get("reward_risk") if t.get("reward_risk") is not None else "—",
                             t.get("reason") or ""] for t in pts],
                hovertemplate=(f"<b>{strat}</b> {'买入' if side == 'buy' else '卖出'} %{{x}}<br>"
                               "成交价 %{customdata[2]} · 数量 %{customdata[0]}<br>"
                               "形态 %{customdata[1]} · R:R %{customdata[5]}<br>"
                               "止损 %{customdata[3]} · 目标 %{customdata[4]}<br>"
                               "理由 %{customdata[6]}<extra></extra>")), row=1, col=1)

        # trade-plan stop/target segments for each buy (extend to its matched sell or +8 bars)
        summary = summarize_strategy_trades(trades, last_close)
        rt_by_buy = {(rt["buy_date"], round(rt["buy_price"], 4)): rt for rt in summary["_round_trips"]}
        for t in trades:
            if t.get("side") != "buy" or t.get("price") is None or t.get("date") not in date_idx:
                continue
            i0 = date_idx[t["date"]]
            rt = rt_by_buy.get((t["date"], round(float(t["price"]), 4)))
            i1 = date_idx.get(rt["sell_date"], min(i0 + 8, len(dates) - 1)) if rt else min(i0 + 8, len(dates) - 1)
            xseg = [dates[i0], dates[i1]]
            for lvl, lvl_color, dash in ((t.get("stop_price"), BAD, "dash"),
                                         (t.get("target_1"), GOOD, "dash"),
                                         (t.get("target_2"), GOOD, "dot")):
                if lvl is None:
                    continue
                fig.add_trace(go.Scatter(x=xseg, y=[float(lvl), float(lvl)], mode="lines",
                                         line=dict(color=lvl_color, width=1, dash=dash),
                                         legendgroup=strat, showlegend=False, hoverinfo="skip"),
                              row=1, col=1)
            # holding shade + buy->sell connector colored by P&L
            if rt:
                win = rt["pnl"] > 0
                fig.add_vrect(x0=t["date"], x1=rt["sell_date"], row=1, col=1, line_width=0,
                              fillcolor=(GOOD if win else BAD), opacity=0.06)
                fig.add_trace(go.Scatter(
                    x=[t["date"], rt["sell_date"]], y=[rt["buy_price"], rt["sell_price"]], mode="lines",
                    line=dict(color=(GOOD if win else BAD), width=1.4, dash="solid"),
                    legendgroup=strat, showlegend=False,
                    hovertemplate=(f"{strat} 回合 P&L {rt['pnl']:+.2f}"
                                   + (f" · {rt['r_mult']:+.2f}R" if rt["r_mult"] is not None else "")
                                   + "<extra></extra>")), row=1, col=1)

    # --- volume ---
    vol_colors = [GOOD if closes[i] >= opens[i] else BAD for i in range(len(closes))]
    fig.add_trace(go.Bar(x=dates, y=volumes, name="成交量", marker_color=vol_colors,
                         showlegend=False, opacity=0.75), row=2, col=1)
    fig.add_trace(go.Scatter(x=dates, y=_sma(volumes, 20), name="量MA20", mode="lines",
                             line=dict(color="#f0a500", width=1), showlegend=False), row=2, col=1)

    # --- RSI ---
    fig.add_trace(go.Scatter(x=dates, y=_rsi(closes, 14), name="RSI", mode="lines",
                             line=dict(color="#38bdf8", width=1.3), showlegend=False), row=3, col=1)
    for lvl in (70, 30):
        fig.add_hline(y=lvl, line=dict(color="rgba(230,237,246,0.25)", width=1, dash="dash"),
                      row=3, col=1)

    # --- MACD ---
    macd, signal, hist = _macd(closes)
    fig.add_trace(go.Bar(x=dates, y=hist, name="MACD柱",
                         marker_color=[GOOD if h >= 0 else BAD for h in hist], showlegend=False),
                  row=4, col=1)
    fig.add_trace(go.Scatter(x=dates, y=macd, name="DIF", mode="lines",
                             line=dict(color="#3b82f6", width=1.1)), row=4, col=1)
    fig.add_trace(go.Scatter(x=dates, y=signal, name="DEA", mode="lines",
                             line=dict(color="#f0a500", width=1.1)), row=4, col=1)

    fig.update_layout(
        height=860, template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=PANEL,
        font=dict(color=TEXT), margin=dict(l=10, r=60, t=46, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                    bgcolor="rgba(0,0,0,0)"),
        hovermode="x unified", dragmode="pan", bargap=0.05,
    )
    # date axis: hide weekends, range buttons on the bottom panel, crosshair spikes, right y-axis
    fig.update_xaxes(gridcolor=GRID, showspikes=True, spikemode="across", spikesnap="cursor",
                     spikethickness=1, spikecolor="rgba(230,237,246,0.4)",
                     rangebreaks=[dict(bounds=["sat", "mon"])])
    fig.update_yaxes(gridcolor=GRID, side="right", showspikes=True, spikethickness=1,
                     spikecolor="rgba(230,237,246,0.4)")
    fig.update_yaxes(range=[0, 100], row=3, col=1)
    fig.update_xaxes(
        rangeslider_visible=False,
        rangeselector=dict(
            buttons=[dict(count=1, label="1M", step="month", stepmode="backward"),
                     dict(count=3, label="3M", step="month", stepmode="backward"),
                     dict(count=6, label="6M", step="month", stepmode="backward"),
                     dict(step="all", label="全部")],
            bgcolor="#161b27", activecolor="#3b82f6", font=dict(color=TEXT), y=1.06),
        row=4, col=1,
    )
    return fig
