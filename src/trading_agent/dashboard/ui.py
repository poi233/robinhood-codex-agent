"""Reusable read-only UI toolkit for the Dashboard v3 redesign (C4).

Everything here is presentation-only: it never reads or writes trading state.
The helpers exist so each chart can render KPI cards, verdict chips, day-over-day
deltas, benchmark comparisons and a "what / how / action" guidance box in one line.

中文为主：所有面向用户的文案默认中文。内部字段名通过 ``COLUMN_LABELS`` 翻译成中文列名后再展示，
界面上不再出现 H2/K1/E4 这类内部代号。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

import pandas as pd
import streamlit as st

try:  # altair is a transitive streamlit dep; guard so import never breaks the app.
    import altair as alt
except Exception:  # pragma: no cover - altair always present with streamlit
    alt = None  # type: ignore[assignment]


# --- Premium dark palette -------------------------------------------------

GOOD = "#16c784"   # 绿 — 好
WARN = "#f0a500"   # 黄 — 一般
BAD = "#ea3943"    # 红 — 差
NEUTRAL = "#8a99b3"  # 灰 — 中性 / 无数据
ACCENT = "#3b82f6"  # 主题强调蓝
CARD_BG = "#161b27"
CARD_BORDER = "#222a3a"


@dataclass(frozen=True)
class Verdict:
    """好坏判定结果：颜色 + emoji + 中文标签。"""

    level: str          # "good" | "warn" | "bad" | "neutral"
    color: str
    emoji: str
    label: str


_VERDICT_PRESETS: dict[str, Verdict] = {
    "good": Verdict("good", GOOD, "🟢", "良好"),
    "warn": Verdict("warn", WARN, "🟡", "一般"),
    "bad": Verdict("bad", BAD, "🔴", "偏差"),
    "neutral": Verdict("neutral", NEUTRAL, "⚪", "无数据"),
}


def verdict(
    value: float | None,
    *,
    good: float,
    warn: float,
    higher_is_better: bool = True,
    labels: tuple[str, str, str] | None = None,
) -> Verdict:
    """把一个数值按阈值映射成 🟢良好 / 🟡一般 / 🔴偏差。

    ``higher_is_better`` 控制方向（如填单率越高越好；空仓率越低越好）。
    当 ``value`` 缺失时返回中性灰，绝不报错。
    """

    if value is None:
        return _VERDICT_PRESETS["neutral"]
    try:
        v = float(value)
    except (TypeError, ValueError):
        return _VERDICT_PRESETS["neutral"]

    if higher_is_better:
        level = "good" if v >= good else "warn" if v >= warn else "bad"
    else:
        level = "good" if v <= good else "warn" if v <= warn else "bad"

    base = _VERDICT_PRESETS[level]
    if labels:
        idx = {"good": 0, "warn": 1, "bad": 2}[level]
        return Verdict(base.level, base.color, base.emoji, labels[idx])
    return base


# --- Central thresholds (好坏判定的统一来源) ------------------------------
#
# 调阈值只改这里。每项: (good, warn, higher_is_better, (好/一般/差 文案))
THRESHOLDS: dict[str, tuple[float, float, bool, tuple[str, str, str]]] = {
    "fill_rate_pct": (70.0, 40.0, True, ("成交顺畅", "成交一般", "成交困难")),
    "no_trade_rate_pct": (40.0, 70.0, False, ("出手积极", "偏谨慎", "几乎空仓")),
    "win_rate_pct": (55.0, 45.0, True, ("胜率占优", "胜率持平", "胜率偏低")),
    "mean_return_pct": (0.5, 0.0, True, ("正期望", "持平", "负期望")),
    "ic": (0.05, 0.0, True, ("有预测力", "弱信号", "无/反向")),
    "t_stat": (2.0, 1.0, True, ("统计显著", "趋势性", "噪音")),
    "coverage_pct": (90.0, 70.0, True, ("数据充足", "略有缺口", "覆盖不足")),
    "slippage_bps": (10.0, 25.0, False, ("滑点可控", "滑点偏高", "滑点严重")),
}


def verdict_for(metric: str, value: float | None) -> Verdict:
    """按 ``THRESHOLDS`` 里登记的口径给某指标判定好坏。未登记返回中性。"""

    spec = THRESHOLDS.get(metric)
    if spec is None:
        return _VERDICT_PRESETS["neutral"]
    good, warn, hib, labels = spec
    return verdict(value, good=good, warn=warn, higher_is_better=hib, labels=labels)


# --- Number formatting ----------------------------------------------------

def fmt_number(value: Any, *, digits: int = 2) -> str:
    if value is None or value == "":
        return "—"
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def fmt_pct(value: Any, *, digits: int = 1) -> str:
    if value is None or value == "":
        return "—"
    try:
        return f"{float(value):,.{digits}f}%"
    except (TypeError, ValueError):
        return str(value)


def fmt_currency(value: Any, *, digits: int = 2) -> str:
    if value is None or value == "":
        return "—"
    try:
        return f"${float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


@dataclass(frozen=True)
class Delta:
    """同比变化（vs 上一交易日 / 上一快照）。"""

    text: str
    good: bool | None  # True 改善 / False 恶化 / None 持平或未知


def delta_vs_prev(
    curr: float | None,
    prev: float | None,
    *,
    higher_is_better: bool = True,
    pct_points: bool = False,
    suffix: str = "",
) -> Delta | None:
    """算 curr-prev 的变化，返回带方向的中文 delta（▲/▼ + 数值 vs 上一期）。

    缺任一侧返回 None（卡片就不显示 delta）。``pct_points`` 时差值按百分点展示。
    """

    if curr is None or prev is None:
        return None
    try:
        diff = float(curr) - float(prev)
    except (TypeError, ValueError):
        return None
    if abs(diff) < 1e-9:
        return Delta("持平 vs 上一期", None)
    arrow = "▲" if diff > 0 else "▼"
    magnitude = f"{abs(diff):,.1f}{'pp' if pct_points else suffix}"
    improved = (diff > 0) if higher_is_better else (diff < 0)
    return Delta(f"{arrow} {magnitude} vs 上一期", improved)


# --- One-time theming ------------------------------------------------------

_CSS = f"""
<style>
.kpi-card {{
  background: {CARD_BG};
  border: 1px solid {CARD_BORDER};
  border-left: 4px solid {NEUTRAL};
  border-radius: 12px;
  padding: 14px 16px;
  margin-bottom: 8px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.35);
}}
.kpi-card.good {{ border-left-color: {GOOD}; }}
.kpi-card.warn {{ border-left-color: {WARN}; }}
.kpi-card.bad  {{ border-left-color: {BAD}; }}
.kpi-label {{ font-size: 0.78rem; color: {NEUTRAL}; letter-spacing: .02em; }}
.kpi-value {{ font-size: 1.7rem; font-weight: 700; line-height: 1.25; margin-top: 2px; }}
.kpi-sub {{ font-size: 0.78rem; margin-top: 3px; }}
.kpi-up   {{ color: {GOOD}; }}
.kpi-down {{ color: {BAD}; }}
.kpi-flat {{ color: {NEUTRAL}; }}
.guidance-box {{
  background: rgba(59,130,246,0.07);
  border: 1px solid rgba(59,130,246,0.25);
  border-radius: 10px;
  padding: 10px 14px;
  margin-bottom: 12px;
  font-size: 0.86rem;
}}
.guidance-box b {{ color: {ACCENT}; }}
</style>
"""


def inject_theme() -> None:
    """注入一次性 CSS + 启用统一的 Altair 深色图表主题。幂等。"""

    if not st.session_state.get("_c4_theme_injected"):
        st.markdown(_CSS, unsafe_allow_html=True)
        st.session_state["_c4_theme_injected"] = True
    _enable_altair_theme()


def _altair_theme() -> dict:
    return {
        "config": {
            "background": "transparent",
            "view": {"stroke": "transparent"},
            "axis": {
                "labelColor": "#c7d1e0",
                "titleColor": "#c7d1e0",
                "gridColor": "rgba(255,255,255,0.06)",
                "domainColor": CARD_BORDER,
            },
            "legend": {"labelColor": "#c7d1e0", "titleColor": "#c7d1e0"},
            "range": {"category": [ACCENT, GOOD, WARN, BAD, "#a855f7", "#06b6d4"]},
            "bar": {"color": ACCENT},
        }
    }


def _enable_altair_theme() -> None:
    if alt is None:
        return
    try:
        alt.themes.register("c4_dark", _altair_theme)
        alt.themes.enable("c4_dark")
    except Exception:  # pragma: no cover - altair API drift shouldn't break the app
        pass


# --- KPI card --------------------------------------------------------------

def kpi_card(
    container: Any,
    label: str,
    value: str,
    *,
    vd: Verdict | None = None,
    delta: Delta | None = None,
    note: str | None = None,
) -> None:
    """渲染一张带好坏色条 + 同比 delta + 可选说明的 KPI 卡片。

    ``container`` 是 ``st.columns(...)`` 里的某一列（或 ``st``）。
    """

    level = vd.level if vd and vd.level != "neutral" else ""
    sub_parts: list[str] = []
    if vd is not None:
        sub_parts.append(f"<span style='color:{vd.color}'>{vd.emoji} {vd.label}</span>")
    if delta is not None:
        cls = "kpi-up" if delta.good else "kpi-down" if delta.good is False else "kpi-flat"
        sub_parts.append(f"<span class='{cls}'>{delta.text}</span>")
    if note:
        sub_parts.append(f"<span class='kpi-flat'>{note}</span>")
    sub = (" · ".join(sub_parts)) if sub_parts else ""
    html = (
        f"<div class='kpi-card {level}'>"
        f"<div class='kpi-label'>{label}</div>"
        f"<div class='kpi-value'>{value}</div>"
        + (f"<div class='kpi-sub'>{sub}</div>" if sub else "")
        + "</div>"
    )
    container.markdown(html, unsafe_allow_html=True)


def guidance_box(what: str, how: str, action: str) -> None:
    """每个小节顶部的「这是什么 / 怎么看 / 建议做什么」引导卡。"""

    st.markdown(
        f"<div class='guidance-box'>"
        f"<b>这是什么</b>：{what}<br>"
        f"<b>怎么看</b>：{how}<br>"
        f"<b>建议</b>：{action}"
        f"</div>",
        unsafe_allow_html=True,
    )


def vs_benchmark(strategy_value: float | None, bench_value: float | None, *, label: str = "vs SPY") -> str:
    """基准对比：返回一句「跑赢/跑输 大盘 X」的中文小结。"""

    if strategy_value is None or bench_value is None:
        return f"{label}：基准数据不足"
    diff = float(strategy_value) - float(bench_value)
    if abs(diff) < 1e-9:
        return f"{label}：与基准持平"
    verb = "跑赢" if diff > 0 else "跑输"
    return f"{label}：{verb}大盘 {abs(diff):,.2f}"


# --- Chinese column labels + pretty tables --------------------------------
#
# 把裸字段名翻译成中文列名（界面上不再出现内部缩写 / snake_case）。
COLUMN_LABELS: Mapping[str, str] = {
    "symbol": "标的",
    "candidate_score": "综合评分",
    "score_status": "评分状态",
    "technical_score": "技术分",
    "catalyst_score": "催化分",
    "dsa_score": "DSA分",
    "kronos_score": "Kronos分",
    "quote_score": "报价分",
    "is_watchlist": "观察名单",
    "is_tradable": "可交易",
    "trade_readiness_score": "交易就绪分",
    "price_setup_score": "价格形态分",
    "timestamp": "时间",
    "decision": "决策",
    "side": "方向",
    "setup_type": "形态",
    "blocked_reasons": "拦截原因",
    "confidence": "置信度",
    "order_id": "订单号",
    "status": "状态",
    "quantity": "数量",
    "limit_price": "限价",
    "fill_price": "成交价",
    "notional": "名义额",
    "reason_codes": "理由码",
    "run_date": "运行日",
    "reason": "原因",
    "count": "次数",
    "strategy_id": "策略版本",
    "run_days": "运行天数",
    "fill_rate_pct": "成交率%",
    "no_trade_rate_pct": "空仓率%",
    "total_realized_pnl": "累计已实现盈亏",
    "avg_realized_pnl_per_day": "日均已实现盈亏",
    "avg_candidate_score": "平均综合评分",
    "avg_trade_readiness_score": "平均就绪分",
    "top_blocked_reason": "最常见拦截",
    "factor_alpha_score": "因子α分",
    "coverage": "覆盖率",
    "risk_flags": "风险标记",
    "advisory_rank_delta": "叠加排名增量",
    "base_trade_readiness_score": "基础就绪分",
    "final_trade_readiness_score": "最终就绪分",
    "size_multiplier": "仓位乘子",
    "block_buy": "禁止买入",
    "ai_layers": "AI信号层",
    "regime": "市场状态",
    "thesis": "投资逻辑",
    "win_rate_pct": "胜率%",
    "mean_return_pct": "平均收益%",
}


def label_of(field: str) -> str:
    return COLUMN_LABELS.get(field, field)


def pretty_table(
    rows: Iterable[Mapping[str, Any]] | pd.DataFrame,
    *,
    columns: list[str] | None = None,
    rename: Mapping[str, str] | None = None,
) -> None:
    """统一表格：自动把字段名翻译成中文列名后用 ``st.dataframe`` 展示。

    ``columns`` 限定/排序展示列；``rename`` 可覆盖默认中文名。缺数据显示空表不报错。
    """

    df = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(list(rows))
    if df.empty:
        st.dataframe(df, use_container_width=True, hide_index=True)
        return
    if columns:
        keep = [c for c in columns if c in df.columns]
        if keep:
            df = df[keep]
    mapping = {col: (rename.get(col) if rename and col in rename else label_of(col)) for col in df.columns}
    df = df.rename(columns=mapping)
    st.dataframe(df, use_container_width=True, hide_index=True)
