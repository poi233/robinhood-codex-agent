"""K线复盘 (candlestick review) figure builder — read-only, presentation only.

Builds an interactive Plotly figure: candlesticks + moving averages + per-strategy
buy/sell markers + volume + MACD, so you can see how each strategy traded a stock.
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

# Distinct colors per strategy overlay (champion first).
STRATEGY_COLORS = ["#3b82f6", "#f0a500", "#a855f7", "#06b6d4", "#ec4899", "#84cc16"]


def _sma(values: list[float], window: int) -> list[float | None]:
    out: list[float | None] = []
    run = 0.0
    for i, v in enumerate(values):
        run += v
        if i >= window:
            run -= values[i - window]
        out.append(round(run / window, 4) if i >= window - 1 else None)
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
        zeros = [0.0] * len(closes)
        return zeros, zeros, zeros
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd = [a - b for a, b in zip(ema12, ema26)]
    signal = _ema(macd, 9)
    hist = [m - s for m, s in zip(macd, signal)]
    return macd, signal, hist


def build_kline_figure(
    symbol: str,
    ohlcv: list[dict[str, Any]],
    trades_by_strategy: dict[str, list[dict[str, Any]]],
    *,
    selected_strategies: list[str] | None = None,
) -> go.Figure:
    dates = [str(r.get("timestamp") or "")[:10] for r in ohlcv]
    opens = [float(r.get("open") or 0) for r in ohlcv]
    highs = [float(r.get("high") or 0) for r in ohlcv]
    lows = [float(r.get("low") or 0) for r in ohlcv]
    closes = [float(r.get("close") or 0) for r in ohlcv]
    volumes = [float(r.get("volume") or 0) for r in ohlcv]

    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.03,
        row_heights=[0.6, 0.18, 0.22],
        subplot_titles=(f"{symbol} 日K + 买卖点", "成交量", "MACD (12/26/9)"),
    )

    fig.add_trace(
        go.Candlestick(
            x=dates, open=opens, high=highs, low=lows, close=closes, name="K线",
            increasing_line_color=GOOD, decreasing_line_color=BAD,
            increasing_fillcolor=GOOD, decreasing_fillcolor=BAD,
        ),
        row=1, col=1,
    )
    for window, color in ((20, "#f0a500"), (50, "#a855f7")):
        sma = _sma(closes, window)
        fig.add_trace(
            go.Scatter(x=dates, y=sma, name=f"SMA{window}", mode="lines",
                       line=dict(color=color, width=1.4), connectgaps=False),
            row=1, col=1,
        )

    # Per-strategy buy/sell markers (triangle-up = buy, triangle-down = sell),
    # colored by strategy so different strategies are visually separable.
    strategies = selected_strategies if selected_strategies is not None else list(trades_by_strategy.keys())
    for idx, strat in enumerate(strategies):
        trades = trades_by_strategy.get(strat) or []
        color = STRATEGY_COLORS[idx % len(STRATEGY_COLORS)]
        for side, sym_marker in (("buy", "triangle-up"), ("sell", "triangle-down")):
            pts = [t for t in trades if t.get("side") == side and t.get("price") is not None]
            if not pts:
                continue
            fig.add_trace(
                go.Scatter(
                    x=[t["date"] for t in pts],
                    y=[float(t["price"]) for t in pts],
                    name=f"{strat} · {'买入' if side == 'buy' else '卖出'}",
                    mode="markers",
                    marker=dict(symbol=sym_marker, size=12, color=color,
                                line=dict(width=1, color="#0e1117")),
                    customdata=[[t.get("quantity"), t.get("reason") or ""] for t in pts],
                    hovertemplate=(f"<b>{strat}</b> {'买入' if side == 'buy' else '卖出'}<br>"
                                   "日期 %{x}<br>价格 %{y}<br>数量 %{customdata[0]}<br>"
                                   "理由 %{customdata[1]}<extra></extra>"),
                ),
                row=1, col=1,
            )

    vol_colors = [GOOD if closes[i] >= opens[i] else BAD for i in range(len(closes))]
    fig.add_trace(
        go.Bar(x=dates, y=volumes, name="成交量", marker_color=vol_colors, showlegend=False),
        row=2, col=1,
    )

    macd, signal, hist = _macd(closes)
    hist_colors = [GOOD if h >= 0 else BAD for h in hist]
    fig.add_trace(go.Bar(x=dates, y=hist, name="MACD柱", marker_color=hist_colors, showlegend=False),
                  row=3, col=1)
    fig.add_trace(go.Scatter(x=dates, y=macd, name="DIF", mode="lines",
                             line=dict(color="#3b82f6", width=1.2)), row=3, col=1)
    fig.add_trace(go.Scatter(x=dates, y=signal, name="DEA", mode="lines",
                             line=dict(color="#f0a500", width=1.2)), row=3, col=1)

    fig.update_layout(
        height=720, template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(color=TEXT), margin=dict(l=10, r=10, t=40, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        xaxis_rangeslider_visible=False, hovermode="x unified", dragmode="pan",
    )
    fig.update_xaxes(gridcolor=GRID, rangeslider_visible=False)
    fig.update_yaxes(gridcolor=GRID)
    # Skip weekend/holiday gaps so candles are contiguous.
    fig.update_xaxes(type="category", showticklabels=False, row=1, col=1)
    fig.update_xaxes(type="category", showticklabels=False, row=2, col=1)
    fig.update_xaxes(type="category", nticks=10, row=3, col=1)
    return fig
