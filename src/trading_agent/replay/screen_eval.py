"""O4 — selection-layer effectiveness report.

Ties the weekly screener's picks to forward returns: do the names O1 added actually go up and
beat SPY? Did demoted names underperform? Does ``screen_score`` predict forward returns (Rank IC)?

Read-only and point-in-time: forward returns are recomputed from yfinance history off the durable
per-week ``runtime/screener/<date>/universe_change.json`` snapshots (added/demoted + a
``screen_scores`` cross-section). Empty until the weekly screener has applied and enough future
bars exist — then it fills in automatically. Never trades, never mutates anything.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import read_json
from trading_agent.replay.component_attribution import _spearman_ic
from trading_agent.replay.forward_returns import (
    _entry_index,
    _forward_returns_from_bars,
    default_price_loader,
)

PriceLoader = Callable[[str, str, str], list[tuple[str, float]]]

DEFAULT_HORIZONS = (5, 21, 63)
DEFAULT_BENCHMARK = "SPY"


def default_screen_eval_report_path(agent_root: Path) -> Path:
    return build_runtime_paths(agent_root).runtime_dir / "analytics" / "screen_eval_report.json"


def default_screen_eval_md_path(agent_root: Path) -> Path:
    return build_runtime_paths(agent_root).runtime_dir / "analytics" / "screen_eval_report.md"


def _screener_dir(agent_root: Path) -> Path:
    return build_runtime_paths(agent_root).runtime_dir / "screener"


def _screener_dates(agent_root: Path, *, since: str | None, until: str | None) -> list[str]:
    base = _screener_dir(agent_root)
    if not base.is_dir():
        return []
    dates = []
    for child in base.iterdir():
        if not child.is_dir():
            continue
        rd = child.name
        if since and rd < since:
            continue
        if until and rd > until:
            continue
        if (child / "universe_change.json").exists():
            dates.append(rd)
    return sorted(dates)


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 6) if values else None


def _summarize(returns_by_h: dict[int, list[float]], excess_by_h: dict[int, list[float]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for horizon in sorted(returns_by_h):
        rets = returns_by_h[horizon]
        exc = excess_by_h.get(horizon, [])
        out[str(horizon)] = {
            "count": len(rets),
            "mean_return": _mean(rets),
            "mean_excess_vs_benchmark": _mean(exc),
            "win_rate_vs_benchmark": round(sum(1 for e in exc if e > 0) / len(exc), 4) if exc else None,
        }
    return out


def build_screen_eval(
    agent_root: Path,
    *,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    benchmark: str = DEFAULT_BENCHMARK,
    since: str | None = None,
    until: str | None = None,
    price_loader: PriceLoader = default_price_loader,
) -> dict[str, Any]:
    """Compute the selection-layer effectiveness report. Returns ``status=insufficient_data`` (not an
    error) when there are no screener runs or no future bars yet."""
    dates = _screener_dates(agent_root, since=since, until=until)
    if not dates:
        return {"status": "insufficient_data", "reason": "no_screener_runs", "horizons": list(horizons)}

    # Gather picks per screener date.
    added: list[tuple[str, str, float | None]] = []   # (date, symbol, factor_score)
    demoted: list[tuple[str, str]] = []               # (date, symbol)
    screen_scores: dict[str, dict[str, float]] = {}   # date -> {symbol: screen_score}
    for rd in dates:
        change = read_json(_screener_dir(agent_root) / rd / "universe_change.json")
        for rec in change.get("added") or []:
            sym = str(rec.get("symbol") or "").upper()
            if sym:
                added.append((rd, sym, rec.get("factor_score")))
        for sym in change.get("demoted") or []:
            demoted.append((rd, str(sym).upper()))
        scores = change.get("screen_scores") or {}
        if isinstance(scores, dict):
            screen_scores[rd] = {str(k).upper(): float(v) for k, v in scores.items() if isinstance(v, (int, float))}

    symbols = {s for _, s, _ in added} | {s for _, s in demoted}
    for per in screen_scores.values():
        symbols |= set(per)
    if not symbols:
        return {"status": "insufficient_data", "reason": "no_picks", "horizons": list(horizons), "screener_runs": len(dates)}

    # Price window covering the largest horizon.
    max_h = max(horizons)
    start = min(dates)
    end = (date.fromisoformat(max(dates)) + timedelta(days=max_h * 2 + 10)).isoformat()
    bench_key = benchmark.upper()
    series: dict[str, list[tuple[str, float]]] = {sym: price_loader(sym, start, end) for sym in symbols}
    bench_bars = series.get(bench_key) or price_loader(bench_key, start, end)

    bench_cache: dict[str, dict[int, float | None]] = {}

    def _bench(rd: str) -> dict[int, float | None]:
        if rd not in bench_cache:
            bench_cache[rd] = _forward_returns_from_bars(bench_bars or [], rd, horizons)
        return bench_cache[rd]

    def _ret_excess(rd: str, sym: str) -> tuple[dict[int, float | None], dict[int, float | None]]:
        rets = _forward_returns_from_bars(series.get(sym) or [], rd, horizons)
        bench = _bench(rd)
        excess = {
            h: (round(rets[h] - bench[h], 6) if rets.get(h) is not None and bench.get(h) is not None else None)
            for h in horizons
        }
        return rets, excess

    # 1) Added-symbol forward returns + excess.
    added_r: dict[int, list[float]] = {h: [] for h in horizons}
    added_e: dict[int, list[float]] = {h: [] for h in horizons}
    matched_added = 0
    for rd, sym, _score in added:
        rets, excess = _ret_excess(rd, sym)
        if any(v is not None for v in rets.values()):
            matched_added += 1
        for h in horizons:
            if rets.get(h) is not None:
                added_r[h].append(rets[h])
            if excess.get(h) is not None:
                added_e[h].append(excess[h])

    # 2) Demoted-symbol forward returns + excess (expect underperformance if cap-demote is shedding well).
    demoted_r: dict[int, list[float]] = {h: [] for h in horizons}
    demoted_e: dict[int, list[float]] = {h: [] for h in horizons}
    for rd, sym in demoted:
        rets, excess = _ret_excess(rd, sym)
        for h in horizons:
            if rets.get(h) is not None:
                demoted_r[h].append(rets[h])
            if excess.get(h) is not None:
                demoted_e[h].append(excess[h])

    # 3) screen_score Rank IC vs forward return (pooled across dates), per horizon.
    ic: dict[str, float | None] = {}
    ic_n: dict[str, int] = {}
    for h in horizons:
        pairs: list[tuple[float, float]] = []
        for rd, per in screen_scores.items():
            for sym, score in per.items():
                ret = _forward_returns_from_bars(series.get(sym) or [], rd, (h,)).get(h)
                if ret is not None:
                    pairs.append((score, ret))
        ic[str(h)] = round(_spearman_ic(pairs), 4) if _spearman_ic(pairs) is not None else None
        ic_n[str(h)] = len(pairs)

    return {
        "status": "ok",
        "generated_at": date.today().isoformat(),
        "benchmark": bench_key,
        "horizons": list(horizons),
        "screener_runs": len(dates),
        "added_count": len(added),
        "added_matched": matched_added,
        "demoted_count": len(demoted),
        "added": _summarize(added_r, added_e),
        "demoted": _summarize(demoted_r, demoted_e),
        "screen_score_ic": {h: {"ic": ic[h], "n": ic_n[h]} for h in ic},
    }


def format_screen_eval_markdown(report: dict[str, Any]) -> str:
    if report.get("status") != "ok":
        return (
            "# 选股有效性报告（O4）\n\n"
            f"_暂无足够数据：{report.get('reason', report.get('status'))}_。"
            "每周选股跑几周、且有未来价格 bar 后即可计算。\n"
        )
    lines = [
        "# 选股有效性报告（O4）",
        "",
        f"基准：{report['benchmark']}　·　screener 运行 {report['screener_runs']} 次　·　"
        f"新增 {report['added_count']}（匹配到价 {report['added_matched']}）　·　降级 {report['demoted_count']}",
        "",
        "## 新增票 forward return（vs 基准超额）",
        "| horizon | 样本 | 平均收益 | 平均超额 | 跑赢基准率 |",
        "|---|---:|---:|---:|---:|",
    ]
    for h, row in report["added"].items():
        lines.append(
            f"| {h}d | {row['count']} | {row['mean_return']} | {row['mean_excess_vs_benchmark']} | {row['win_rate_vs_benchmark']} |"
        )
    lines += ["", "## 被降级票 forward return（期望偏弱）", "| horizon | 样本 | 平均收益 | 平均超额 |", "|---|---:|---:|---:|"]
    for h, row in report["demoted"].items():
        lines.append(f"| {h}d | {row['count']} | {row['mean_return']} | {row['mean_excess_vs_benchmark']} |")
    lines += ["", "## screen_score Rank IC（越高越能预测）", "| horizon | IC | 样本 |", "|---|---:|---:|"]
    for h, row in report["screen_score_ic"].items():
        lines.append(f"| {h}d | {row['ic']} | {row['n']} |")
    lines += ["", "> 样本少时数字噪声大，只看方向。需要 flag 开启后积累几周。"]
    return "\n".join(lines) + "\n"


def write_screen_eval_report(
    agent_root: Path,
    *,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    since: str | None = None,
    until: str | None = None,
    price_loader: PriceLoader = default_price_loader,
) -> tuple[Path, Path]:
    report = build_screen_eval(agent_root, horizons=horizons, since=since, until=until, price_loader=price_loader)
    json_path = default_screen_eval_report_path(agent_root)
    md_path = default_screen_eval_md_path(agent_root)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    import json as _json

    json_path.write_text(_json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(format_screen_eval_markdown(report), encoding="utf-8")
    return json_path, md_path
