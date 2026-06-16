from __future__ import annotations

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


def _collect_pairs(records: list[ForwardReturnRecord], component: str, horizon: int) -> list[tuple[float, float]]:
    pairs: list[tuple[float, float]] = []
    for rec in records:
        ret = rec.returns.get(horizon)
        if ret is None:
            continue
        if component in _TOP_LEVEL_FIELDS:
            score = getattr(rec, component)
        else:
            score = rec.components.get(component)
        if score is None:
            continue
        pairs.append((float(score), float(ret)))
    return pairs


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
