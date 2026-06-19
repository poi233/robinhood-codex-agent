"""Reusable read-only UI toolkit for the Dashboard v3 redesign (C4).

Everything here is presentation-only: it never reads or writes trading state.
The helpers exist so each chart can render KPI cards, verdict chips, day-over-day
deltas, benchmark comparisons and a "what / how / action" guidance box in one line.

中文为主：所有面向用户的文案默认中文。内部字段名通过 ``COLUMN_LABELS`` 翻译成中文列名后再展示，
界面上不再出现 H2/K1/E4 这类内部代号。
"""
from __future__ import annotations

import json
from html import escape
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
PANEL_BG = "#101824"


@dataclass(frozen=True)
class Verdict:
    """好坏判定结果：颜色 + 中文标签。"""

    level: str          # "good" | "warn" | "bad" | "neutral"
    color: str
    marker: str
    label: str


@dataclass(frozen=True)
class PageBrief:
    """统一的页面头部配置。"""

    title: str
    caption: str
    what: str
    how: str
    action: str
    dated: bool = False


@dataclass(frozen=True)
class MetricCard:
    """统一 KPI 卡片配置。"""

    label: str
    value: str
    vd: Verdict | None = None
    delta: Delta | None = None
    note: str | None = None


_VERDICT_PRESETS: dict[str, Verdict] = {
    "good": Verdict("good", GOOD, "", "良好"),
    "warn": Verdict("warn", WARN, "", "一般"),
    "bad": Verdict("bad", BAD, "", "偏差"),
    "neutral": Verdict("neutral", NEUTRAL, "", "无数据"),
}


def verdict(
    value: float | None,
    *,
    good: float,
    warn: float,
    higher_is_better: bool = True,
    labels: tuple[str, str, str] | None = None,
) -> Verdict:
    """把一个数值按阈值映射成良好 / 一般 / 偏差。

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
        return Verdict(base.level, base.color, base.marker, labels[idx])
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
    """算 curr-prev 的变化，返回带方向的中文 delta（上升/下降 + 数值 vs 上一期）。

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
    direction = "上升" if diff > 0 else "下降"
    magnitude = f"{abs(diff):,.1f}{'pp' if pct_points else suffix}"
    improved = (diff > 0) if higher_is_better else (diff < 0)
    return Delta(f"{direction} {magnitude} vs 上一期", improved)


# --- One-time theming ------------------------------------------------------

_CSS = f"""
<style>
.stApp {{
  background:
    radial-gradient(circle at 18% 0%, rgba(22,199,132,0.10), transparent 28%),
    radial-gradient(circle at 82% 6%, rgba(59,130,246,0.12), transparent 30%),
    linear-gradient(180deg, #070b12 0%, #0b111b 45%, #070b12 100%);
}}
header[data-testid="stHeader"] {{ background: transparent; }}
#MainMenu,
footer,
.stDeployButton,
div[data-testid="stToolbar"],
div[data-testid="stDecoration"],
div[data-testid="stElementToolbar"],
svg[data-testid="stElementToolbarButtonIcon"] {{
  display: none !important;
}}
a[href^="#"],
a[href^="#"] svg {{
  display: none !important;
}}
section[data-testid="stSidebar"] {{
  background: linear-gradient(180deg, #101722 0%, #0b111b 100%);
  border-right: 1px solid rgba(148,163,184,0.12);
}}
.block-container {{
  padding-top: 2.4rem;
  padding-bottom: 3rem;
  max-width: 1180px;
}}
.terminal-title {{
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  margin: 2px 0 22px;
  padding-left: 14px;
  border-left: 3px solid {GOOD};
}}
.terminal-title h1 {{
  font-size: 2.05rem;
  line-height: 1.05;
  margin: 0;
  letter-spacing: 0;
}}
.terminal-subtitle {{
  color: {NEUTRAL};
  font-size: .78rem;
}}
div[data-baseweb="tab-list"] {{
  gap: 10px;
  border-bottom: 1px solid rgba(148,163,184,0.15);
  margin-bottom: 18px;
}}
button[data-baseweb="tab"] {{
  height: 36px;
  padding: 0 12px;
  border-radius: 6px 6px 0 0;
  color: #94a3b8;
  background: rgba(15,23,42,0.30);
  border: 1px solid transparent;
  border-bottom: 0;
}}
button[data-baseweb="tab"][aria-selected="true"] {{
  color: #e7eefb;
  background: rgba(22,28,40,0.92);
  border-color: rgba(59,130,246,0.35);
}}
button[data-baseweb="tab"] p {{
  font-size: .86rem;
  font-weight: 700;
}}
span[data-testid="stIconMaterial"] {{
  display: none !important;
}}
div[data-testid="stExpander"] {{
  margin-top: 14px;
  margin-bottom: 14px;
}}
div[data-testid="stExpander"] details {{
  border-radius: 9px;
}}
div[data-testid="stExpander"] summary {{
  padding-top: 12px !important;
  padding-bottom: 12px !important;
}}
div[data-testid="stAlert"] {{
  border-radius: 8px;
  border: 1px solid rgba(148,163,184,0.16);
  background: rgba(17,24,39,0.82);
  box-shadow: inset 3px 0 0 rgba(148,163,184,0.28);
}}
div[data-testid="stAlert"] svg {{
  display: none;
}}
.modebar,
.modebar-container {{
  display: none !important;
}}
.hero-panel {{
  position: relative;
  overflow: hidden;
  border: 1px solid rgba(94,234,212,0.22);
  background:
    radial-gradient(circle at 7% 18%, rgba(22,199,132,0.20), transparent 22%),
    linear-gradient(110deg, rgba(16,24,36,0.98), rgba(18,31,45,0.95) 58%, rgba(13,20,31,0.98));
  border-radius: 10px;
  padding: 24px 24px 20px;
  box-shadow: 0 18px 60px rgba(0,0,0,0.35);
  margin-bottom: 24px;
}}
.hero-panel::after {{
  content: "";
  position: absolute;
  inset: -40% -18% auto auto;
  width: 420px;
  height: 260px;
  background: linear-gradient(135deg, rgba(59,130,246,0.16), rgba(22,199,132,0.06));
  transform: rotate(14deg);
  pointer-events: none;
}}
.hero-grid {{
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: 138px minmax(0, 1fr);
  gap: 24px;
  align-items: center;
}}
.score-ring {{
  width: 112px;
  height: 112px;
  border-radius: 999px;
  display: grid;
  place-items: center;
  background:
    radial-gradient(circle at center, #111a27 58%, transparent 59%),
    conic-gradient({GOOD} calc(var(--score) * 1%), rgba(148,163,184,0.18) 0);
  box-shadow: inset 0 0 0 1px rgba(255,255,255,0.04), 0 0 36px rgba(22,199,132,0.15);
}}
.score-ring span {{
  font-size: 2rem;
  font-weight: 800;
  color: #f7fbff;
}}
.score-ring small {{
  display: block;
  margin-top: -6px;
  font-size: .58rem;
  color: {NEUTRAL};
  text-align: center;
}}
.hero-kicker {{
  color: {GOOD};
  font-size: .74rem;
  font-weight: 700;
  margin-bottom: 6px;
}}
.hero-headline {{
  font-size: 1.36rem;
  font-weight: 800;
  line-height: 1.25;
  color: #f8fbff;
  margin-bottom: 7px;
}}
.hero-copy {{
  color: #b9c5d6;
  max-width: 760px;
  font-size: .86rem;
  line-height: 1.55;
}}
.hero-metrics {{
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-top: 20px;
}}
.hero-metric {{
  background: rgba(255,255,255,0.055);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 7px;
  padding: 12px 13px;
}}
.hero-metric .label {{
  color: {NEUTRAL};
  font-size: .68rem;
  margin-bottom: 2px;
}}
.hero-metric .value {{
  font-size: 1rem;
  font-weight: 800;
  color: #f8fbff;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}}
.card-strip {{
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 13px;
  margin: 18px 0 18px;
}}
.pick-card {{
  border: 1px solid rgba(148,163,184,0.15);
  border-top: 3px solid {ACCENT};
  border-radius: 8px;
  background: linear-gradient(180deg, rgba(20,28,42,0.96), rgba(13,19,29,0.98));
  padding: 13px 13px;
  min-height: 108px;
}}
.pick-card.good {{ border-top-color: {GOOD}; }}
.pick-card.warn {{ border-top-color: {WARN}; }}
.pick-symbol {{
  font-size: 1.05rem;
  font-weight: 850;
  color: #f8fbff;
  margin-bottom: 4px;
}}
.pick-score {{
  color: {GOOD};
  font-weight: 800;
  font-size: .94rem;
}}
.pick-meta {{
  color: {NEUTRAL};
  font-size: .68rem;
  line-height: 1.35;
  margin-top: 5px;
}}
.bar-list {{
  display: grid;
  gap: 10px;
  border: 1px solid rgba(148,163,184,0.14);
  border-radius: 8px;
  background: rgba(10,15,24,0.72);
  padding: 14px 15px;
  margin-top: 12px;
  margin-bottom: 18px;
}}
.bar-row {{
  display: grid;
  grid-template-columns: minmax(72px, 150px) minmax(0, 1fr) 74px;
  gap: 10px;
  align-items: center;
  min-height: 24px;
}}
.bar-label {{
  color: #e7eefb;
  font-size: .76rem;
  font-weight: 700;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}}
.bar-track {{
  height: 8px;
  border-radius: 999px;
  overflow: hidden;
  background: rgba(148,163,184,0.16);
}}
.bar-fill {{
  height: 100%;
  width: var(--w);
  border-radius: inherit;
  background: linear-gradient(90deg, {ACCENT}, {GOOD});
}}
.bar-value {{
  color: {NEUTRAL};
  font-size: .72rem;
  text-align: right;
  font-variant-numeric: tabular-nums;
}}
.section-band {{
  margin: 22px 0 18px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border: 1px solid rgba(148,163,184,0.14);
  border-left: 3px solid {ACCENT};
  border-radius: 8px;
  padding: 14px 16px;
  background: linear-gradient(90deg, rgba(20,28,42,0.92), rgba(10,15,24,0.70));
}}
.section-band h3 {{
  margin: 0;
  font-size: .98rem;
}}
.section-band span {{
  color: {NEUTRAL};
  font-size: .72rem;
  text-align: right;
}}
.kpi-card {{
  background: {CARD_BG};
  border: 1px solid {CARD_BORDER};
  border-left: 4px solid {NEUTRAL};
  border-radius: 8px;
  padding: 13px 15px;
  margin-bottom: 12px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.35);
}}
.kpi-card.good {{ border-left-color: {GOOD}; }}
.kpi-card.warn {{ border-left-color: {WARN}; }}
.kpi-card.bad  {{ border-left-color: {BAD}; }}
.kpi-label {{ font-size: 0.72rem; color: {NEUTRAL}; letter-spacing: .02em; }}
.kpi-value {{
  font-size: 1.26rem;
  font-weight: 700;
  line-height: 1.18;
  margin-top: 2px;
  overflow-wrap: anywhere;
}}
.kpi-sub {{ font-size: 0.7rem; margin-top: 5px; }}
.kpi-up   {{ color: {GOOD}; }}
.kpi-down {{ color: {BAD}; }}
.kpi-flat {{ color: {NEUTRAL}; }}
.guidance-box {{
  background: rgba(59,130,246,0.07);
  border: 1px solid rgba(59,130,246,0.25);
  border-radius: 8px;
  padding: 10px 14px;
  margin-bottom: 18px;
  font-size: 0.86rem;
}}
.guidance-box b {{ color: {ACCENT}; }}
section.main h1 {{ margin-bottom: 0.15rem; }}
section.main h2 {{ margin-top: 1.05rem; margin-bottom: 0.65rem; }}
section.main h3 {{ margin-top: 0.9rem; margin-bottom: 0.55rem; }}
div[data-testid="stVerticalBlock"] {{ gap: 0.9rem; }}
div[data-testid="stHorizontalBlock"] {{ gap: 0.85rem; }}
div[data-testid="stDataFrame"] {{
  border: 1px solid rgba(148,163,184,0.14);
  border-radius: 8px;
  overflow: hidden;
  margin-top: 12px;
  margin-bottom: 20px;
}}
@media (max-width: 900px) {{
  .hero-grid {{ grid-template-columns: 1fr; }}
  .hero-metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  .card-strip {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  .section-band {{ align-items: flex-start; flex-direction: column; }}
  .section-band span {{ text-align: left; }}
}}
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
    # altair>=5.5 moved theming to ``alt.theme``; fall back to the legacy
    # ``alt.themes`` registry on older versions. Never let theming break the app.
    try:
        if hasattr(alt, "theme") and hasattr(alt.theme, "register"):
            alt.theme.register("c4_dark", enable=True)(_altair_theme)
        else:
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
        sub_parts.append(f"<span style='color:{vd.color}'>{vd.label}</span>")
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


def guidance_expander(label: str, *, what: str, how: str, action: str) -> None:
    with st.expander(label):
        guidance_box(what=what, how=how, action=action)


def app_title(title: str, subtitle: str) -> None:
    st.markdown(
        f"<div class='terminal-title'><h1>{escape(title)}</h1>"
        f"<div class='terminal-subtitle'>{escape(subtitle)}</div></div>",
        unsafe_allow_html=True,
    )


def section_band(title: str, caption: str = "") -> None:
    st.markdown(
        f"<div class='section-band'><h3>{escape(title)}</h3><span>{escape(caption)}</span></div>",
        unsafe_allow_html=True,
    )


def page_header(brief: PageBrief, *, run_date: str | None = None, show_help: bool = False) -> None:
    title = f"{brief.title} — {run_date}" if brief.dated and run_date else brief.title
    section_band(title, brief.caption)
    if show_help:
        guidance_box(what=brief.what, how=brief.how, action=brief.action)


def detail_expander(label: str, *, show_detail: bool = False, expanded: bool = False):
    return st.expander(label, expanded=bool(show_detail or expanded))


def metric_row(cards: list[MetricCard], *, max_columns: int = 4) -> None:
    if not cards:
        return
    count = min(max_columns, max(1, len(cards)))
    cols = st.columns(count)
    for index, card in enumerate(cards):
        kpi_card(
            cols[index % count],
            card.label,
            card.value,
            vd=card.vd,
            delta=card.delta,
            note=card.note,
        )


def hero_panel(
    *,
    kicker: str,
    headline: str,
    copy: str,
    score: int | float,
    score_label: str,
    metrics: list[tuple[str, str]],
) -> None:
    score_clamped = max(0, min(100, int(round(float(score)))))
    metric_html = "".join(
        "<div class='hero-metric'>"
        f"<div class='label'>{escape(label)}</div>"
        f"<div class='value'>{escape(value)}</div>"
        "</div>"
        for label, value in metrics[:4]
    )
    st.markdown(
        "<div class='hero-panel'>"
        "<div class='hero-grid'>"
        f"<div class='score-ring' style='--score:{score_clamped}'><div><span>{score_clamped}</span><small>{escape(score_label)}</small></div></div>"
        "<div>"
        f"<div class='hero-kicker'>{escape(kicker)}</div>"
        f"<div class='hero-headline'>{escape(headline)}</div>"
        f"<div class='hero-copy'>{escape(copy)}</div>"
        "</div>"
        "</div>"
        f"<div class='hero-metrics'>{metric_html}</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def pick_cards(rows: list[Mapping[str, Any]], *, limit: int = 5) -> None:
    cards = []
    for row in rows[:limit]:
        score = row.get("candidate_score")
        try:
            score_value = float(score)
        except (TypeError, ValueError):
            score_value = 0.0
        tone = "good" if row.get("is_tradable") else "warn"
        status = display_value(row.get("score_status") or "")
        readiness = fmt_number(row.get("trade_readiness_score")) if row.get("trade_readiness_score") is not None else "—"
        cards.append(
            f"<div class='pick-card {tone}'>"
            f"<div class='pick-symbol'>{escape(str(row.get('symbol') or '—'))}</div>"
            f"<div class='pick-score'>{score_value:.2f}</div>"
            f"<div class='pick-meta'>{escape(status)}<br>交易就绪 {escape(readiness)} · {'可交易' if row.get('is_tradable') else '观察'}</div>"
            "</div>"
        )
    if not cards:
        return
    st.markdown(f"<div class='card-strip'>{''.join(cards)}</div>", unsafe_allow_html=True)


def bar_list(items: list[tuple[str, float]], *, value_label: str, limit: int = 12) -> None:
    if not items:
        st.caption("暂无可展示明细。")
        return
    cleaned = [(str(label), float(value)) for label, value in items if value is not None]
    if not cleaned:
        st.caption("暂无可展示明细。")
        return
    if any(value < 0 for _, value in cleaned):
        pretty_table([{"item": label, "value": value} for label, value in cleaned[:limit]],
                     rename={"item": "项目", "value": value_label})
        return
    top = sorted(cleaned, key=lambda row: row[1], reverse=True)[:limit]
    max_value = max((value for _, value in top), default=0.0)
    if max_value <= 0:
        pretty_table([{"item": label, "value": value} for label, value in top],
                     rename={"item": "项目", "value": value_label})
        return
    rows = []
    for label, value in top:
        width = max(2.0, min(100.0, value / max_value * 100.0))
        rows.append(
            "<div class='bar-row'>"
            f"<div class='bar-label'>{escape(label)}</div>"
            f"<div class='bar-track'><div class='bar-fill' style='--w:{width:.1f}%'></div></div>"
            f"<div class='bar-value'>{escape(fmt_number(value))}</div>"
            "</div>"
        )
    st.markdown(f"<div class='bar-list'>{''.join(rows)}</div>", unsafe_allow_html=True)


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
    "category": "类别",
    "artifact": "数据项",
    "metric": "指标",
    "value": "内容",
    "date_start": "开始日",
    "date_end": "结束日",
    "orders_total": "订单数",
    "total_orders": "总订单数",
    "orders_filled": "已成交订单",
    "total_evaluations": "评估次数",
    "would_trade": "可交易次数",
    "shadow_days": "影子天数",
    "evaluations": "评估数",
    "recommend_promote": "建议升级",
    "blocking_reasons": "阻塞原因",
    "module": "模块",
    "severity": "级别",
    "message": "说明",
    "mutation": "变更",
    "validation_status": "验证状态",
    "proposal_id": "提案ID",
    "status": "状态",
    "proposal_count": "提案数",
    "active_shadow_count": "活跃影子数",
    "calibration_sample_size": "校准样本数",
    "run_date_count": "运行日数",
    "champion_fill_rate_pct": "冠军成交率%",
}


def label_of(field: str) -> str:
    return COLUMN_LABELS.get(field, field)


VALUE_LABELS: Mapping[str, str] = {
    "blocked": "不交易",
    "would_trade": "可交易",
    "no_trade": "不交易",
    "premarket_plan": "盘前计划",
    "postmarket_summary": "盘后总结",
    "dsa_signals_generated": "DSA信号生成",
    "outside_entry_zone": "不在入场区",
    "no_trade_zone": "禁止交易区",
    "chase_blocked": "追高拦截",
    "insufficient_data": "数据不足",
    "scored": "已评分",
    "ok": "正常",
}


def display_value(value: Any) -> str:
    text = str(value)
    label = VALUE_LABELS.get(text)
    return f"{label}（{text}）" if label else text


def _format_cell(value: Any) -> Any:
    if value is None:
        return "—"
    try:
        if pd.isna(value):
            return "—"
    except (TypeError, ValueError):
        pass
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return "—"
        if stripped[:1] in "[{":
            try:
                return _format_cell(json.loads(stripped))
            except json.JSONDecodeError:
                return display_value(value)
        return display_value(value)
    if isinstance(value, list):
        if not value:
            return "—"
        return "、".join(str(_format_cell(item)) for item in value)
    if isinstance(value, dict):
        if not value:
            return "—"
        parts = []
        for key, item in value.items():
            formatted = _format_cell(item)
            if formatted == "—":
                continue
            parts.append(f"{label_of(str(key))}: {formatted}")
        return "；".join(parts) if parts else "—"
    return str(value)


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
        st.caption("暂无可展示明细。")
        return
    if columns:
        keep = [c for c in columns if c in df.columns]
        if keep:
            df = df[keep]
    mapping = {col: (rename.get(col) if rename and col in rename else label_of(col)) for col in df.columns}
    df = df.map(_format_cell) if hasattr(df, "map") else df.applymap(_format_cell)
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str)
    df = df.rename(columns=mapping)
    st.dataframe(df, width="stretch", hide_index=True)
