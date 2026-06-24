"""Q2 — strategy diversity metrics + low-correlation selection.

"Run more strategies" only buys more information if the strategies are *different*. Ten near-clone
breakout variants over the same days give redundant data, not 10× signal. This module measures how
different the standing strategies actually are, from data already on disk:

  - **return correlation**: Pearson correlation of each pair's daily paper equity returns (from the
    isolated ledgers + the champion curve). Low pairwise correlation == "covers different parts of
    the data".
  - **entry overlap**: Jaccard overlap of the (run_date, symbol) sets each challenger entered (from
    shadow_decisions). High overlap == same trades under a different name.
  - **greedy diverse selection**: pick the highest-edge strategy, then repeatedly add the next one
    that still has positive edge AND stays below a correlation ceiling to everything already picked.
    This maximises information per forward-paper slot instead of "top N by PnL" (which tends to pick
    correlated near-duplicates).

Read-only: consumes equity curves + shadow_decisions, writes nothing of its own (the evaluator
embeds the result in its report). Champion is keyed ``__champion__``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from trading_agent.core.context import build_experiment_runtime_paths, build_runtime_paths

CHAMPION_KEY = "__champion__"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _daily_equity_returns(equity_rows: list[dict[str, Any]]) -> dict[str, float]:
    """Map day → fractional change of end-of-day total_equity vs the previous day's. Multiple rows
    per day collapse to the last (chronological) total_equity for that day."""
    by_day: dict[str, float] = {}
    for row in sorted(equity_rows, key=lambda r: str(r.get("timestamp") or "")):
        equity = row.get("total_equity")
        if equity is None:
            continue
        day = str(row.get("timestamp") or "")[:10]
        if day:
            by_day[day] = float(equity)
    days = sorted(by_day)
    returns: dict[str, float] = {}
    for prev_day, day in zip(days, days[1:]):
        prev = by_day[prev_day]
        if prev:
            returns[day] = by_day[day] / prev - 1.0
    return returns


def strategy_daily_returns(
    agent_root: Path,
    *,
    run_dates: list[str],
    challenger_ids: list[str],
    include_champion: bool = True,
) -> dict[str, dict[str, float]]:
    """Per-strategy {day → daily return} from each isolated challenger ledger (+ the champion)."""
    out: dict[str, dict[str, float]] = {}
    for strategy_id in challenger_ids:
        rows: list[dict[str, Any]] = []
        for run_date in run_dates:
            exp = build_experiment_runtime_paths(agent_root, run_date=run_date, strategy_id=strategy_id)
            rows.extend(_read_jsonl(exp.paper_equity_curve_path))
        returns = _daily_equity_returns(rows)
        if returns:
            out[strategy_id] = returns
    if include_champion:
        rows = []
        for run_date in run_dates:
            rows.extend(_read_jsonl(build_runtime_paths(agent_root, run_date=run_date).paper_equity_curve_path))
        returns = _daily_equity_returns(rows)
        if returns:
            out[CHAMPION_KEY] = returns
    return out


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:  # correlation on < 3 overlapping days is noise, not signal
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    dx = sum((x - mean_x) ** 2 for x in xs) ** 0.5
    dy = sum((y - mean_y) ** 2 for y in ys) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return round(cov / (dx * dy), 4)


def pairwise_return_correlation(returns_by_strategy: dict[str, dict[str, float]]) -> dict[str, dict[str, float | None]]:
    ids = sorted(returns_by_strategy)
    matrix: dict[str, dict[str, float | None]] = {}
    for a in ids:
        matrix[a] = {}
        for b in ids:
            if a == b:
                matrix[a][b] = 1.0
                continue
            ra, rb = returns_by_strategy[a], returns_by_strategy[b]
            common = sorted(set(ra) & set(rb))
            matrix[a][b] = _pearson([ra[d] for d in common], [rb[d] for d in common])
    return matrix


def entry_sets_from_decisions(decisions_by_strategy: dict[str, list[dict[str, Any]]]) -> dict[str, set[tuple[str, str]]]:
    """Per strategy, the set of (run_date, symbol) it would have entered (would_trade decisions)."""
    out: dict[str, set[tuple[str, str]]] = {}
    for strategy_id, decisions in decisions_by_strategy.items():
        entries: set[tuple[str, str]] = set()
        for decision in decisions:
            if decision.get("decision") == "would_trade" and decision.get("symbol"):
                entries.add((str(decision.get("run_date")), str(decision.get("symbol")).upper()))
        out[strategy_id] = entries
    return out


def jaccard_overlap(entry_sets: dict[str, set[tuple[str, str]]]) -> dict[str, dict[str, float | None]]:
    ids = sorted(entry_sets)
    matrix: dict[str, dict[str, float | None]] = {}
    for a in ids:
        matrix[a] = {}
        for b in ids:
            if a == b:
                matrix[a][b] = 1.0 if entry_sets[a] else None
                continue
            sa, sb = entry_sets[a], entry_sets[b]
            union = len(sa | sb)
            matrix[a][b] = round(len(sa & sb) / union, 4) if union else None
    return matrix


def greedy_diverse_selection(
    edge_by_id: dict[str, float | None],
    corr_matrix: dict[str, dict[str, float | None]],
    *,
    max_corr: float = 0.7,
    min_edge: float = 0.0,
) -> list[str]:
    """Pick the highest-edge strategy, then repeatedly add the next strategy whose edge ≥ ``min_edge``
    and whose maximum correlation to the already-selected set is ≤ ``max_corr``. Unknown correlation
    (too few common days) is treated as "not known to be redundant" and does not exclude."""
    eligible = [sid for sid, edge in edge_by_id.items() if edge is not None and edge >= min_edge]
    eligible.sort(key=lambda sid: (-(edge_by_id[sid] or 0.0), sid))
    selected: list[str] = []
    for sid in eligible:
        if not selected:
            selected.append(sid)
            continue
        corrs = [corr_matrix.get(sid, {}).get(other) for other in selected]
        known = [c for c in corrs if c is not None]
        if not known or max(known) <= max_corr:
            selected.append(sid)
    return selected


def build_diversity_report(
    agent_root: Path,
    *,
    run_dates: list[str],
    challenger_ids: list[str],
    decisions_by_strategy: dict[str, list[dict[str, Any]]],
    edge_by_id: dict[str, float | None],
    max_corr: float = 0.7,
    min_edge: float = 0.0,
) -> dict[str, Any]:
    """Assemble the diversity block embedded in the promotion report."""
    returns = strategy_daily_returns(agent_root, run_dates=run_dates, challenger_ids=challenger_ids)
    correlation = pairwise_return_correlation(returns)
    overlap = jaccard_overlap(entry_sets_from_decisions(decisions_by_strategy))
    selected = greedy_diverse_selection(edge_by_id, correlation, max_corr=max_corr, min_edge=min_edge)
    return {
        "return_correlation": correlation,
        "entry_overlap": overlap,
        "diverse_selection": selected,
        "params": {"max_corr": max_corr, "min_edge": min_edge},
        "note": (
            "low pairwise correlation / entry overlap = genuinely different strategies; "
            "diverse_selection greedily maximises edge per forward slot under the correlation ceiling"
        ),
    }
