from __future__ import annotations

from collections import defaultdict
from typing import Any

from trading_agent.replay.forward_returns import ForwardReturnRecord

# Headline scores treated as attributable components alongside the premarket sub-scores.
_TOP_LEVEL_FIELDS = ("candidate_score", "trade_readiness_score", "price_setup_score")


def _spearman_ic(pairs: list[tuple[float, float]]) -> float | None:
    """Spearman rank correlation (information coefficient) between score and forward return.
    Returns None when there are <3 samples or either side has zero variance (rank IC undefined)."""
    n = len(pairs)
    if n < 3:
        return None

    def _ranks(values: list[float]) -> list[float]:
        order = sorted(range(n), key=lambda i: values[i])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and values[order[j + 1]] == values[order[i]]:
                j += 1
            avg_rank = (i + j) / 2 + 1
            for k in range(i, j + 1):
                ranks[order[k]] = avg_rank
            i = j + 1
        return ranks

    xs = _ranks([p[0] for p in pairs])
    ys = _ranks([p[1] for p in pairs])
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x <= 0 or var_y <= 0:
        return None
    return cov / (var_x * var_y) ** 0.5


def _component_value(rec: ForwardReturnRecord, component: str) -> float | None:
    if component in _TOP_LEVEL_FIELDS:
        return getattr(rec, component)
    return rec.components.get(component)


def _collect_pairs(records: list[ForwardReturnRecord], component: str, horizon: int) -> list[tuple[float, float]]:
    pairs: list[tuple[float, float]] = []
    for rec in records:
        ret = rec.returns.get(horizon)
        if ret is None:
            continue
        score = _component_value(rec, component)
        if score is None:
            continue
        pairs.append((float(score), float(ret)))
    return pairs


def _ic_time_series(records: list[ForwardReturnRecord], component: str, horizon: int) -> list[float]:
    """Cross-sectional Spearman IC computed *within each run date*, returned as a time series. This
    is the standard way to judge a signal: a component is reliable when its per-date IC is positive
    on average and stable across dates, not just when the pooled IC happens to be high."""
    by_date: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for rec in records:
        ret = rec.returns.get(horizon)
        if ret is None:
            continue
        score = _component_value(rec, component)
        if score is None:
            continue
        by_date[rec.run_date].append((float(score), float(ret)))
    ics: list[float] = []
    for _date, pairs in sorted(by_date.items()):
        ic = _spearman_ic(pairs)
        if ic is not None:
            ics.append(ic)
    return ics


def _ic_stats(ics: list[float]) -> dict[str, Any]:
    """Mean / sample-std / t-stat of an IC time series. The t-stat (mean / stderr) is the headline
    'is this IC real or noise?' number — |t| ≳ 2 over enough dates is the usual significance bar."""
    n = len(ics)
    if n == 0:
        return {"periods": 0, "mean_ic": None, "std_ic": None, "t_stat": None}
    mean_ic = sum(ics) / n
    if n < 2:
        return {"periods": n, "mean_ic": round(mean_ic, 4), "std_ic": None, "t_stat": None}
    var = sum((ic - mean_ic) ** 2 for ic in ics) / (n - 1)
    std = var ** 0.5
    t_stat = (mean_ic / (std / n ** 0.5)) if std > 0 else None
    return {
        "periods": n,
        "mean_ic": round(mean_ic, 4),
        "std_ic": round(std, 4),
        "t_stat": round(t_stat, 3) if t_stat is not None else None,
    }


def component_attribution(records: list[ForwardReturnRecord], *, horizon: int) -> list[dict[str, Any]]:
    """Rank scoring components by their forward-return information coefficient (Spearman IC) at
    `horizon`. This is the direct evidence base for E2 weight recalibration: a high positive IC
    means the component predicts winners; an IC near zero means it adds no alpha. Components are
    the three headline scores plus whatever premarket sub-scores appear in the records."""
    component_names: list[str] = list(_TOP_LEVEL_FIELDS)
    seen = set(component_names)
    for rec in records:
        for name in rec.components:
            if name not in seen:
                seen.add(name)
                component_names.append(name)

    rows: list[dict[str, Any]] = []
    for name in component_names:
        pairs = _collect_pairs(records, name, horizon)
        rows.append({"component": name, "n": len(pairs), "ic": _spearman_ic(pairs)})
    # Rank by |IC| desc; undefined (None) IC sinks to the bottom.
    rows.sort(key=lambda r: (r["ic"] is not None, abs(r["ic"]) if r["ic"] is not None else 0.0), reverse=True)
    return rows


def _component_names(records: list[ForwardReturnRecord]) -> list[str]:
    names: list[str] = list(_TOP_LEVEL_FIELDS)
    seen = set(names)
    for rec in records:
        for name in rec.components:
            if name not in seen:
                seen.add(name)
                names.append(name)
    return names


def component_ic_summary(
    records: list[ForwardReturnRecord], *, horizons: tuple[int, ...]
) -> list[dict[str, Any]]:
    """Multi-horizon Rank IC summary per component. For each component and horizon, reports the
    pooled IC (all candidate-return pairs together) plus the per-run-date IC time-series stats
    (mean / std / t-stat). This is the rigorous evidence base for E2 weight recalibration: prefer
    components whose mean per-date IC is sizeable *and* whose t-stat clears the noise floor, not
    components that merely have one lucky pooled number. Components are ranked by |mean IC| at the
    shortest horizon (the most-populated, lowest-variance estimate)."""
    rows: list[dict[str, Any]] = []
    primary_h = horizons[0] if horizons else 1
    for name in _component_names(records):
        per_horizon: dict[str, Any] = {}
        for h in horizons:
            pooled = _spearman_ic(_collect_pairs(records, name, h))
            stats = _ic_stats(_ic_time_series(records, name, h))
            per_horizon[str(h)] = {"pooled_ic": round(pooled, 4) if pooled is not None else None, **stats}
        primary = per_horizon.get(str(primary_h), {})
        rows.append({
            "component": name,
            "horizons": per_horizon,
            "_rank_key": abs(primary.get("mean_ic")) if primary.get("mean_ic") is not None else -1.0,
        })
    rows.sort(key=lambda r: r["_rank_key"], reverse=True)
    for r in rows:
        r.pop("_rank_key", None)
    return rows
