"""Q1 — historical setup replay screener (the discovery harness).

Replays any entry setup over **all historical run dates** and reports, per setup, how its
hypothetical entries would have fared. This inverts the current "guess a setup → wait weeks of
forward paper" loop into "screen N setups over all history in seconds → forward-paper only the
survivors".

How it works (point-in-time, no look-ahead in the decision):
  1. ``discover_run_dates`` finds every persisted run under ``runtime/state/runs/``.
  2. For each run date, ``load_policy_inputs`` rebuilds the exact ``PolicyInputs`` the engine saw
     that day (candidate_scores, trader_watch_levels/key_levels, quotes, research, profile).
  3. ``rank_candidates`` ranks the candidates exactly as the live engine would; ``decide_buy_price``
     runs the strategy's setup stack. Every non-blocked decision is a hypothetical entry.
  4. Only THEN do we look forward: the daily price series (injected ``PriceLoader``) decides whether
     the entry hit ``target_1`` before ``stop_price`` within ``lookahead`` trading days, and the
     mean forward return over the same horizon.

Champion-specific portfolio state (positions / open orders / daily usage) is neutralised so the
screen measures each setup's *intrinsic* price edge identically across setups — genuine
point-in-time gates (daily_plan, data_status, risk_overlay, quote freshness, technical levels) are
kept. Read-only: writes only ``runtime/analytics/setup_screen.{json,md}``, never champion/paper
state. Close-based daily-bar approximation (mirrors ``setup_outcomes``): intraday touches are
understated, but it is directionally correct for the question that matters — *which setup wins*.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from trading_agent.policy.candidate_selector import rank_candidates
from trading_agent.policy.loaders import load_policy_inputs
from trading_agent.policy.models import PolicyInputs
from trading_agent.policy.price_policy import decide_buy_price
from trading_agent.policy.setups import SETUP_REGISTRY
from trading_agent.replay.analysis import discover_run_dates
from trading_agent.replay.forward_returns import PriceLoader, _entry_index, default_price_loader
from trading_agent.replay.significance import benjamini_hochberg, binomial_sf

_APPROX_NOTE = (
    "close-based daily-bar approximation (intraday touches understated; assumes the hypothetical "
    "limit fills) — directionally correct for which setup wins"
)


@dataclass(frozen=True)
class HypotheticalFill:
    run_date: str
    symbol: str
    setup_type: str
    limit_price: float
    stop_price: float | None
    target_1: float | None
    reward_risk: float | None


def _neutralize_portfolio_state(inputs: PolicyInputs) -> None:
    """Zero champion-specific portfolio/usage state so the screen measures each setup's intrinsic
    price edge identically across setups. Genuine point-in-time tradeability gates are untouched."""
    inputs.positions = {}
    inputs.open_orders = []
    inputs.daily_usage = {}


def generate_hypothetical_fills(
    agent_root: Path,
    *,
    run_dates: list[str],
    profile_name: str | None = None,
    setups: list[str] | None = None,
    risk_tier: int = 0,
    max_per_day: int | None = None,
) -> list[HypotheticalFill]:
    """Replay the setup stack over ``run_dates`` and return every non-blocked hypothetical entry.

    ``setups`` (if given) overrides the profile's setup stack, so an arbitrary setup/stack can be
    screened without a saved policy_profile. One bad run date never aborts the screen.
    """
    fills: list[HypotheticalFill] = []
    for run_date in run_dates:
        try:
            inputs = load_policy_inputs(
                agent_root,
                run_date=run_date,
                trading_mode="paper",
                risk_tier=risk_tier,
                policy_profile_name=profile_name,
            )
        except Exception:
            continue
        if setups is not None:
            profile = dict(inputs.policy_profile or {})
            profile["setups"] = list(setups)
            inputs.policy_profile = profile
        _neutralize_portfolio_state(inputs)
        try:
            ranked, _blocked = rank_candidates(inputs)
        except Exception:
            continue
        taken = 0
        for candidate in ranked:
            decision = decide_buy_price(inputs, candidate)
            if decision.blocked_reason is not None:
                continue
            limit = decision.limit_price
            if not limit or limit <= 0:
                continue
            fills.append(
                HypotheticalFill(
                    run_date=run_date,
                    symbol=candidate.symbol,
                    setup_type=decision.setup_type,
                    limit_price=float(limit),
                    stop_price=decision.stop_price,
                    target_1=decision.target_1,
                    reward_risk=decision.reward_risk,
                )
            )
            taken += 1
            if max_per_day is not None and taken >= max_per_day:
                break
    return fills


def _evaluate_fills(
    fills: list[HypotheticalFill],
    *,
    lookahead: int,
    price_loader: PriceLoader,
) -> dict[str, dict[str, Any]]:
    """Aggregate per setup_type: target-first / stop-first within ``lookahead`` trading days
    (close-based, mirroring ``setup_outcomes``) + mean forward return over the same horizon.

    The price series is loaded once per unique symbol, so screening many setups over the same names
    costs no extra network calls.
    """
    if not fills:
        return {}
    symbols = {fill.symbol for fill in fills}
    start = min(fill.run_date for fill in fills)
    end = (date.fromisoformat(max(fill.run_date for fill in fills)) + timedelta(days=lookahead * 2 + 7)).isoformat()
    series = {symbol: price_loader(symbol, start, end) for symbol in symbols}

    agg: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"fills": 0, "target_first": 0, "stop_first": 0, "undecided": 0, "fwd": []}
    )
    for fill in fills:
        bucket = agg[fill.setup_type]
        bucket["fills"] += 1
        bars = series.get(fill.symbol) or []
        entry_idx = _entry_index(bars, fill.run_date)
        if entry_idx is None or fill.target_1 is None or fill.stop_price is None:
            bucket["undecided"] += 1
            continue
        outcome = "undecided"
        for _day, close in bars[entry_idx + 1 : entry_idx + 1 + lookahead]:
            if close >= float(fill.target_1):
                outcome = "target_first"
                break
            if close <= float(fill.stop_price):
                outcome = "stop_first"
                break
        bucket[outcome] += 1
        entry_close = bars[entry_idx][1]
        horizon_idx = entry_idx + lookahead
        if horizon_idx < len(bars) and entry_close:
            bucket["fwd"].append(bars[horizon_idx][1] / entry_close - 1.0)
    return agg


def _rows_from_agg(agg: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for setup_type, data in sorted(agg.items()):
        decided = data["target_first"] + data["stop_first"]
        fwd = data["fwd"]
        rows.append(
            {
                "setup_type": setup_type,
                "fills": data["fills"],
                "target_first": data["target_first"],
                "stop_first": data["stop_first"],
                "undecided": data["undecided"],
                "win_rate": round(data["target_first"] / decided, 4) if decided else None,
                "mean_fwd_return": round(sum(fwd) / len(fwd), 6) if fwd else None,
                "n_fwd": len(fwd),
                # Q5: one-sided p that win rate beats a coin flip, so small samples are not trusted.
                "p_value": binomial_sf(data["target_first"], decided) if decided else None,
            }
        )
    return _apply_fdr(rows)


def _apply_fdr(rows: list[dict[str, Any]], *, alpha: float = 0.05) -> list[dict[str, Any]]:
    """Q5: control the False Discovery Rate across the screened setups — annotate each row with the
    BH-adjusted q-value and a ``significant`` flag, so "the best of N setups" isn't just luck."""
    adjusted = benjamini_hochberg({r["setup_type"]: r["p_value"] for r in rows if r.get("p_value") is not None}, alpha)
    for row in rows:
        verdict = adjusted.get(row["setup_type"], {})
        row["q_value"] = verdict.get("q")
        row["significant"] = bool(verdict.get("significant"))
    return rows


def screen_setups(
    agent_root: Path,
    *,
    lookahead: int = 5,
    since: str | None = None,
    until: str | None = None,
    profile_name: str | None = None,
    setups: list[str] | None = None,
    risk_tier: int = 0,
    max_per_day: int | None = None,
    price_loader: PriceLoader = default_price_loader,
) -> dict[str, Any]:
    """Screen ONE setup stack (the dispatcher's first-clears-wins) over all history. Rows are broken
    down by the setup that actually fired — use this to see how a profile's stack behaves."""
    run_dates = discover_run_dates(agent_root, since_date=since, until_date=until)
    if not run_dates:
        return {"status": "no_data", "reason": "no run dates under runtime/state/runs/", "run_dates": 0, "fills": 0, "rows": []}
    fills = generate_hypothetical_fills(
        agent_root,
        run_dates=run_dates,
        profile_name=profile_name,
        setups=setups,
        risk_tier=risk_tier,
        max_per_day=max_per_day,
    )
    agg = _evaluate_fills(fills, lookahead=lookahead, price_loader=price_loader)
    return {
        "status": "ok" if fills else "no_fills",
        "mode": "stack",
        "run_dates": len(run_dates),
        "since": since,
        "until": until,
        "lookahead": lookahead,
        "setups": setups,
        "profile": profile_name,
        "fills": len(fills),
        "rows": _rows_from_agg(agg),
        "note": _APPROX_NOTE,
    }


def screen_all_setups(
    agent_root: Path,
    *,
    lookahead: int = 5,
    since: str | None = None,
    until: str | None = None,
    risk_tier: int = 0,
    max_per_day: int | None = None,
    price_loader: PriceLoader = default_price_loader,
) -> dict[str, Any]:
    """Default comparison: screen EACH registered setup in isolation (its full opportunity set, not
    first-clears-wins) → one head-to-head row per setup. This is the "setup × win-rate × forward-
    return × N" table."""
    run_dates = discover_run_dates(agent_root, since_date=since, until_date=until)
    if not run_dates:
        return {"status": "no_data", "reason": "no run dates under runtime/state/runs/", "run_dates": 0, "fills": 0, "rows": []}
    all_fills: list[HypotheticalFill] = []
    for name in sorted(SETUP_REGISTRY):
        all_fills.extend(
            generate_hypothetical_fills(
                agent_root,
                run_dates=run_dates,
                setups=[name],
                risk_tier=risk_tier,
                max_per_day=max_per_day,
            )
        )
    agg = _evaluate_fills(all_fills, lookahead=lookahead, price_loader=price_loader)
    return {
        "status": "ok" if all_fills else "no_fills",
        "mode": "per_setup",
        "run_dates": len(run_dates),
        "since": since,
        "until": until,
        "lookahead": lookahead,
        "setups": sorted(SETUP_REGISTRY),
        "fills": len(all_fills),
        "rows": _rows_from_agg(agg),
        "note": _APPROX_NOTE,
    }


def screen_train_test(
    agent_root: Path,
    *,
    split_date: str,
    lookahead: int = 5,
    since: str | None = None,
    until: str | None = None,
    risk_tier: int = 0,
    max_per_day: int | None = None,
    price_loader: PriceLoader = default_price_loader,
) -> dict[str, Any]:
    """Q5: screen each setup on the TRAIN window (run dates < split_date) and, separately, on the
    held-out TEST window (>= split_date). A setup that only wins in-sample is overfit — compare the
    two tables. ``since``/``until`` further bound the overall window."""
    train_until = split_date if until is None else min(split_date, until)
    train = screen_all_setups(
        agent_root, lookahead=lookahead, since=since, until=train_until,
        risk_tier=risk_tier, max_per_day=max_per_day, price_loader=price_loader,
    )
    test = screen_all_setups(
        agent_root, lookahead=lookahead, since=split_date, until=until,
        risk_tier=risk_tier, max_per_day=max_per_day, price_loader=price_loader,
    )
    return {"status": "ok", "mode": "train_test", "split_date": split_date, "lookahead": lookahead,
            "train": train, "test": test,
            "note": "a setup that wins in TRAIN but not TEST is overfit; trust TEST (held-out)."}


def _screen_table(report: dict[str, Any]) -> str:
    if report.get("status") == "no_data":
        return f"_暂无历史数据：{report.get('reason')}_。\n"
    rows = report.get("rows") or []
    if not rows:
        return f"_扫描了 {report.get('run_dates', 0)} 个交易日，没有任何 setup 产生有效假设入场_。\n"
    horizon = report.get("lookahead", 5)
    out = [
        f"| setup | 假设成交 | 触目标 | 触止损 | 未决 | 胜率 | 平均{horizon}d收益 | 样本 | p | q | 显著 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|:--:|",
    ]
    for row in rows:
        win = row["win_rate"] if row["win_rate"] is not None else "—"
        fwd = row["mean_fwd_return"] if row["mean_fwd_return"] is not None else "—"
        p = row.get("p_value") if row.get("p_value") is not None else "—"
        q = row.get("q_value") if row.get("q_value") is not None else "—"
        sig = "✓" if row.get("significant") else ""
        out.append(
            f"| {row['setup_type']} | {row['fills']} | {row['target_first']} | {row['stop_first']} | "
            f"{row['undecided']} | {win} | {fwd} | {row['n_fwd']} | {p} | {q} | {sig} |"
        )
    return "\n".join(out) + "\n"


def format_setup_screen_markdown(report: dict[str, Any]) -> str:
    if report.get("mode") == "train_test":
        parts = [
            "# 历史 setup 重放筛选 · train/test（Q5）",
            "",
            f"切分日 {report['split_date']}　·　lookahead {report['lookahead']}d",
            "",
            "## TRAIN（样本内，切分日之前）",
            _screen_table(report.get("train") or {}),
            "## TEST（样本外，切分日及之后）",
            _screen_table(report.get("test") or {}),
            f"> {report.get('note', '')}",
        ]
        return "\n".join(parts) + "\n"
    if report.get("status") == "no_data":
        return (
            "# 历史 setup 重放筛选（Q1）\n\n"
            f"_暂无历史数据：{report.get('reason')}_。需要 `runtime/state/runs/` 下有跑过的交易日。\n"
        )
    if not report.get("rows"):
        return (
            "# 历史 setup 重放筛选（Q1）\n\n"
            f"_扫描了 {report.get('run_dates', 0)} 个交易日，没有任何 setup 产生有效假设入场_。\n"
        )
    mode = "每个 setup 独立对比" if report.get("mode") == "per_setup" else "setup 栈（first-clears-wins）"
    horizon = report["lookahead"]
    lines = [
        "# 历史 setup 重放筛选（Q1）",
        "",
        f"模式：{mode}　·　交易日 {report['run_dates']}　·　假设成交 {report['fills']}　·　"
        f"lookahead {horizon}d　·　窗口 {report.get('since') or '全部'} → {report.get('until') or '全部'}",
        "",
        _screen_table(report),
        f"> {report.get('note', '')}",
        "> p=胜率优于掷硬币的单边检验；q/✓=多重比较(BH-FDR α0.05)校正后仍显著。样本少时只看方向。",
    ]
    return "\n".join(lines) + "\n"


def default_setup_screen_report_path(agent_root: Path) -> Path:
    return agent_root / "runtime" / "analytics" / "setup_screen.json"


def default_setup_screen_md_path(agent_root: Path) -> Path:
    return agent_root / "runtime" / "analytics" / "setup_screen.md"


def write_setup_screen_report(
    agent_root: Path,
    *,
    lookahead: int = 5,
    since: str | None = None,
    until: str | None = None,
    profile_name: str | None = None,
    setups: list[str] | None = None,
    risk_tier: int = 0,
    max_per_day: int | None = None,
    split_date: str | None = None,
    price_loader: PriceLoader = default_price_loader,
) -> tuple[Path, Path]:
    """Write ``runtime/analytics/setup_screen.{json,md}``. ``split_date`` → Q5 train/test split;
    else default (no ``setups``/``profile_name``) screens every registered setup head-to-head;
    otherwise screens that specific stack/profile."""
    if split_date:
        report = screen_train_test(
            agent_root, split_date=split_date, lookahead=lookahead, since=since, until=until,
            risk_tier=risk_tier, max_per_day=max_per_day, price_loader=price_loader,
        )
    elif setups or profile_name:
        report = screen_setups(
            agent_root,
            lookahead=lookahead,
            since=since,
            until=until,
            profile_name=profile_name,
            setups=setups,
            risk_tier=risk_tier,
            max_per_day=max_per_day,
            price_loader=price_loader,
        )
    else:
        report = screen_all_setups(
            agent_root,
            lookahead=lookahead,
            since=since,
            until=until,
            risk_tier=risk_tier,
            max_per_day=max_per_day,
            price_loader=price_loader,
        )
    json_path = default_setup_screen_report_path(agent_root)
    md_path = default_setup_screen_md_path(agent_root)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(format_setup_screen_markdown(report), encoding="utf-8")
    return json_path, md_path
