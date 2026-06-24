"""Q4 — data-driven strategy discovery (let the data PROPOSE setups).

Q1 tests setups you already thought of; Q4 mines history for setups you haven't. All read-only,
joining what the engine recorded against realised forward returns:

  - **blocked-reason edge**: for every (day, symbol) the engine did NOT buy (``per_candidate_blocks``
    in the decision log), attribute its forward return to each gate that blocked it. A reason that
    repeatedly blocks names which then RISE is a gate costing money — i.e. a setup waiting to be
    built (e.g. if "no_trade_zone" blocks names that average +3%, build a setup for that zone).
  - **top blocked winners**: the specific (day, symbol) the engine skipped that went up the most,
    with the reasons that blocked them — a concrete "these are the ones you missed" list.
  - **near-threshold**: reuses near_miss — do candidates that *just* missed the trade threshold
    return as well as the ones that cleared it? If so, the threshold is too strict.

Writes only ``runtime/analytics/discovery.{json,md}``. Close-based daily-bar forward returns
(yfinance via the injected loader); graceful no_data / no_forward_returns.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from trading_agent.replay.analysis import collect_decisions, discover_run_dates
from trading_agent.replay.forward_returns import (
    ForwardReturnRecord,
    PriceLoader,
    compute_forward_return_records,
    default_price_loader,
)
from trading_agent.replay.near_miss import load_trade_thresholds, near_threshold_analysis

DEFAULT_HORIZON = 5


def _forward_return_index(records: list[ForwardReturnRecord], horizon: int) -> dict[tuple[str, str], float]:
    """(run_date, SYMBOL) → forward return at ``horizon``, for records that have it."""
    index: dict[tuple[str, str], float] = {}
    for rec in records:
        ret = rec.returns.get(horizon)
        if ret is not None:
            index[(rec.run_date, rec.symbol.upper())] = ret
    return index


def _iter_blocked_candidates(agent_root: Path, run_dates: list[str]):
    """Yield (run_date, SYMBOL, [reasons]) for every blocked candidate in the decision logs."""
    for decision in collect_decisions(agent_root, run_dates=run_dates):
        run_date = str(decision.get("_run_date") or decision.get("run_date") or "")
        per_candidate = decision.get("per_candidate_blocks") or {}
        if not isinstance(per_candidate, dict):
            continue
        for symbol, reasons in per_candidate.items():
            yield run_date, str(symbol).upper(), list(reasons or [])


def blocked_reason_edge(
    agent_root: Path,
    *,
    run_dates: list[str],
    fwd_index: dict[tuple[str, str], float],
    win_threshold: float = 0.0,
) -> list[dict[str, Any]]:
    """Per block reason: how many blocked names had a known forward return, their mean forward
    return, up-rate, and winner count. Sorted by mean forward return desc — the reasons at the top
    are blocking the best-performing names (the strongest "build a setup here" signal)."""
    agg: dict[str, list[float]] = defaultdict(list)
    for run_date, symbol, reasons in _iter_blocked_candidates(agent_root, run_dates):
        ret = fwd_index.get((run_date, symbol))
        if ret is None:
            continue
        for reason in reasons:
            agg[reason].append(ret)
    rows: list[dict[str, Any]] = []
    for reason, rets in agg.items():
        rows.append(
            {
                "reason": reason,
                "blocked_with_known_return": len(rets),
                "mean_fwd_return": round(sum(rets) / len(rets), 6),
                "win_rate": round(sum(1 for r in rets if r > 0) / len(rets), 4),
                "winners_blocked": sum(1 for r in rets if r > win_threshold),
            }
        )
    rows.sort(key=lambda r: r["mean_fwd_return"], reverse=True)
    return rows


def top_blocked_winners(
    agent_root: Path,
    *,
    run_dates: list[str],
    fwd_index: dict[tuple[str, str], float],
    top_k: int = 20,
) -> list[dict[str, Any]]:
    """The (day, symbol) the engine skipped that had the highest forward return + why they were
    blocked — a concrete list of missed winners to mine for a new setup."""
    rows: list[dict[str, Any]] = []
    for run_date, symbol, reasons in _iter_blocked_candidates(agent_root, run_dates):
        ret = fwd_index.get((run_date, symbol))
        if ret is None:
            continue
        rows.append({"run_date": run_date, "symbol": symbol, "fwd_return": round(ret, 6), "blocked_reasons": reasons})
    rows.sort(key=lambda r: r["fwd_return"], reverse=True)
    return rows[:top_k]


def build_discovery_report(
    agent_root: Path,
    *,
    lookahead: int = DEFAULT_HORIZON,
    since: str | None = None,
    until: str | None = None,
    price_loader: PriceLoader = default_price_loader,
    top_k: int = 20,
) -> dict[str, Any]:
    run_dates = discover_run_dates(agent_root, since_date=since, until_date=until)
    if not run_dates:
        return {"status": "no_data", "reason": "no run dates under runtime/state/runs/", "run_dates": 0}
    records = compute_forward_return_records(
        agent_root, horizons=(lookahead,), since=since, until=until, price_loader=price_loader
    )
    fwd_index = _forward_return_index(records, lookahead)
    thresholds = load_trade_thresholds(agent_root, run_dates)
    near = near_threshold_analysis(records, thresholds, horizons=(lookahead,))
    return {
        "status": "ok" if fwd_index else "no_forward_returns",
        "run_dates": len(run_dates),
        "lookahead": lookahead,
        "since": since,
        "until": until,
        "blocked_reason_edge": blocked_reason_edge(agent_root, run_dates=run_dates, fwd_index=fwd_index),
        "top_blocked_winners": top_blocked_winners(agent_root, run_dates=run_dates, fwd_index=fwd_index, top_k=top_k),
        "near_threshold": near,
        "note": (
            "close-based daily-bar forward returns; a reason high in blocked_reason_edge is a gate "
            "blocking winners — a candidate setup to build. Small samples are noisy (see Q5)."
        ),
    }


def format_discovery_markdown(report: dict[str, Any]) -> str:
    if report.get("status") == "no_data":
        return f"# 数据驱动策略发现（Q4）\n\n_暂无历史数据：{report.get('reason')}_。\n"
    if report.get("status") == "no_forward_returns":
        return (
            "# 数据驱动策略发现（Q4）\n\n"
            f"_扫描了 {report.get('run_dates', 0)} 个交易日，但还没有可用的前向收益_"
            "（需要联网拉 yfinance 且有未来 bar）。\n"
        )
    horizon = report["lookahead"]
    lines = [
        "# 数据驱动策略发现（Q4）",
        "",
        f"交易日 {report['run_dates']}　·　lookahead {horizon}d　·　窗口 "
        f"{report.get('since') or '全部'} → {report.get('until') or '全部'}",
        "",
        f"## 被闸门挡掉的赢家（按 reason 的 {horizon}d 前向收益排序）",
        "> 排在前面的 reason 最常挡住随后上涨的票 —— 是「该建一个 setup」的最强信号。",
        "",
        f"| reason | 挡掉(有未来收益) | 平均{horizon}d收益 | 上涨率 | 赢家数 |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in report["blocked_reason_edge"]:
        lines.append(
            f"| {row['reason']} | {row['blocked_with_known_return']} | {row['mean_fwd_return']} | "
            f"{row['win_rate']} | {row['winners_blocked']} |"
        )
    lines += ["", f"## 错过的 top 赢家（被挡但随后 {horizon}d 大涨）", "", f"| 日期 | 标的 | {horizon}d收益 | 被挡原因 |", "|---|---|---:|---|"]
    for row in report["top_blocked_winners"]:
        lines.append(f"| {row['run_date']} | {row['symbol']} | {row['fwd_return']} | {', '.join(row['blocked_reasons'])} |")
    lines += ["", "## near-threshold（trade_threshold 是否太严）", "> near_miss 收益 ≈ 或 > cleared，说明门槛在挡赢家。", ""]
    near = report.get("near_threshold") or {}
    for horizon_key, classes in near.items():
        lines.append(f"### horizon {horizon_key}d")
        lines.append("| 类别 | 样本 | 平均收益 | 上涨率 |")
        lines.append("|---|---:|---:|---:|")
        for cls in ("cleared", "near_miss", "below"):
            data = classes.get(cls, {})
            lines.append(f"| {cls} | {data.get('count', 0)} | {data.get('mean_return')} | {data.get('hit_rate')} |")
        lines.append("")
    lines += [f"> {report.get('note', '')}"]
    return "\n".join(lines) + "\n"


def default_discovery_report_path(agent_root: Path) -> Path:
    return agent_root / "runtime" / "analytics" / "discovery.json"


def default_discovery_md_path(agent_root: Path) -> Path:
    return agent_root / "runtime" / "analytics" / "discovery.md"


def write_discovery_report(
    agent_root: Path,
    *,
    lookahead: int = DEFAULT_HORIZON,
    since: str | None = None,
    until: str | None = None,
    price_loader: PriceLoader = default_price_loader,
    top_k: int = 20,
) -> tuple[Path, Path]:
    report = build_discovery_report(
        agent_root, lookahead=lookahead, since=since, until=until, price_loader=price_loader, top_k=top_k
    )
    json_path = default_discovery_report_path(agent_root)
    md_path = default_discovery_md_path(agent_root)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(format_discovery_markdown(report), encoding="utf-8")
    return json_path, md_path
