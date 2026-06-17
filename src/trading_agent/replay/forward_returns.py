from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import read_json
from trading_agent.replay.analysis import discover_run_dates

DEFAULT_HORIZONS = (1, 5, 21, 63)

# A price loader returns daily (date, close) bars for one symbol, sorted ascending,
# covering at least [start, end]. Injected so tests run without network.
PriceLoader = Callable[[str, str, str], list[tuple[str, float]]]


@dataclass
class ForwardReturnRecord:
    run_date: str
    symbol: str
    candidate_score: float | None
    trade_readiness_score: float | None
    price_setup_score: float | None
    returns: dict[int, float | None]
    components: dict[str, float] = field(default_factory=dict)
    # Excess return over the primary benchmark (default SPY) at each horizon, computed from the
    # same entry date. None when either the candidate or the benchmark return is pending. This is
    # what separates real alpha from a market-beta tailwind in the bucket monotonicity check.
    excess: dict[int, float | None] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_date": self.run_date,
            "symbol": self.symbol,
            "candidate_score": self.candidate_score,
            "trade_readiness_score": self.trade_readiness_score,
            "price_setup_score": self.price_setup_score,
            **{f"fwd_{h}": value for h, value in self.returns.items()},
            **{f"excess_{h}": value for h, value in self.excess.items()},
        }


def default_price_loader(symbol: str, start: str, end: str) -> list[tuple[str, float]]:
    """yfinance daily closes for `symbol` over [start, end]. Returns [] on any failure."""
    try:
        import yfinance as yf
    except Exception:
        return []
    try:
        frame = yf.Ticker(symbol).history(start=start, end=end, interval="1d", auto_adjust=False)
    except Exception:
        return []
    bars: list[tuple[str, float]] = []
    for idx, row in frame.iterrows():
        day = idx.date().isoformat() if hasattr(idx, "date") else str(idx)[:10]
        try:
            bars.append((day, float(row["Close"])))
        except (KeyError, TypeError, ValueError):
            continue
    bars.sort(key=lambda item: item[0])
    return bars


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _candidate_scores_for_run(agent_root: Path, run_date: str) -> dict[str, dict[str, float | None]]:
    """Per-symbol scores for a run date, merging candidate_scores.json (candidate_score) with
    the latest intraday_rankings entry (trade_readiness_score / price_setup_score)."""
    paths = build_runtime_paths(agent_root, run_date=run_date)
    scores: dict[str, dict[str, float | None]] = {}

    if paths.candidate_scores_path.exists():
        payload = read_json(paths.candidate_scores_path)
        symbols = payload.get("symbols") if isinstance(payload, dict) else None
        if isinstance(symbols, dict):
            for symbol, data in symbols.items():
                if not isinstance(data, dict):
                    continue
                components = data.get("components") if isinstance(data.get("components"), dict) else {}
                scores[str(symbol).upper()] = {
                    "candidate_score": _as_float(data.get("total_score") if data.get("total_score") is not None else data.get("score")),
                    "trade_readiness_score": None,
                    "price_setup_score": None,
                    "components": {k: v for k, v in ((name, _as_float(val)) for name, val in components.items()) if v is not None},
                }

    rankings_path = paths.intraday_rankings_log_path
    if rankings_path.exists():
        for line in rankings_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            symbol = str(row.get("symbol") or "").upper()
            if not symbol:
                continue
            entry = scores.setdefault(symbol, {"candidate_score": _as_float(row.get("candidate_score")),
                                               "trade_readiness_score": None, "price_setup_score": None, "components": {}})
            # Latest row wins (file is appended chronologically).
            entry["trade_readiness_score"] = _as_float(row.get("trade_readiness_score"))
            entry["price_setup_score"] = _as_float(row.get("price_setup_score"))

    # H2 auto-pickup: fold factor_alpha + per-factor ranks into components so the dynamic
    # calibration bucketing + IC attribution cover them by name with zero extra code.
    if paths.factor_alpha_path.exists():
        payload = read_json(paths.factor_alpha_path)
        symbols = payload.get("symbols") if isinstance(payload, dict) else None
        if isinstance(symbols, dict):
            for symbol, data in symbols.items():
                if not isinstance(data, dict):
                    continue
                entry = scores.setdefault(str(symbol).upper(), {"candidate_score": None,
                                          "trade_readiness_score": None, "price_setup_score": None, "components": {}})
                comps = entry.setdefault("components", {})
                alpha = _as_float(data.get("factor_alpha_score"))
                if alpha is not None:
                    comps["factor_alpha"] = alpha
                for fname, rank in (data.get("factor_components") or {}).items():
                    val = _as_float(rank)
                    if val is not None:
                        comps[fname] = val
    return scores


def _entry_index(bars: list[tuple[str, float]], run_date: str) -> int | None:
    for index, (day, _close) in enumerate(bars):
        if day >= run_date:
            return index
    return None


def _forward_returns_from_bars(
    bars: list[tuple[str, float]], run_date: str, horizons: tuple[int, ...]
) -> dict[int, float | None]:
    """Per-horizon forward return from the close on (or just after) `run_date`. A horizon with too
    few future bars is None (pending) rather than guessed."""
    entry_idx = _entry_index(bars, run_date)
    returns: dict[int, float | None] = {}
    for horizon in horizons:
        if entry_idx is None or entry_idx + horizon >= len(bars):
            returns[horizon] = None
            continue
        entry_close = bars[entry_idx][1]
        future_close = bars[entry_idx + horizon][1]
        returns[horizon] = round(future_close / entry_close - 1, 6) if entry_close else None
    return returns


def compute_forward_return_records(
    agent_root: Path,
    *,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    since: str | None = None,
    until: str | None = None,
    price_loader: PriceLoader = default_price_loader,
    benchmark: str = "SPY",
) -> list[ForwardReturnRecord]:
    """For each historical run date and scored candidate, compute its forward return at each horizon
    from the close on (or just after) the run date, plus the excess return over `benchmark` (SPY by
    default) measured from the same entry date. A horizon with too few future bars is recorded as
    None (pending) rather than guessed."""
    run_dates = discover_run_dates(agent_root, since_date=since, until_date=until)
    if not run_dates:
        return []

    # Gather (run_date, symbol, scores) and the symbol set.
    per_run: dict[str, dict[str, dict[str, float | None]]] = {rd: _candidate_scores_for_run(agent_root, rd) for rd in run_dates}
    symbols: set[str] = {sym for run in per_run.values() for sym in run}
    if not symbols:
        return []

    # Price window: from the earliest run date to the latest + enough calendar days to cover the
    # largest horizon in trading days (≈ 1.6x + buffer for weekends/holidays).
    max_h = max(horizons) if horizons else 5
    start = min(run_dates)
    end_date = date.fromisoformat(max(run_dates)) + timedelta(days=max_h * 2 + 7)
    end = end_date.isoformat()
    series: dict[str, list[tuple[str, float]]] = {sym: price_loader(sym, start, end) for sym in symbols}

    # Benchmark series (loaded once); benchmark forward returns are cached per run date so excess is
    # the candidate's market-relative move, isolating alpha from a broad-market tailwind.
    bench_key = benchmark.upper()
    bench_bars = series.get(bench_key) if bench_key in symbols else price_loader(bench_key, start, end)
    bench_returns: dict[str, dict[int, float | None]] = {}

    def _benchmark_returns(run_date: str) -> dict[int, float | None]:
        if run_date not in bench_returns:
            bench_returns[run_date] = _forward_returns_from_bars(bench_bars or [], run_date, horizons)
        return bench_returns[run_date]

    records: list[ForwardReturnRecord] = []
    for run_date in run_dates:
        bench = _benchmark_returns(run_date)
        for symbol, score_map in per_run[run_date].items():
            bars = series.get(symbol) or []
            returns = _forward_returns_from_bars(bars, run_date, horizons)
            excess: dict[int, float | None] = {}
            for horizon in horizons:
                own = returns.get(horizon)
                mkt = bench.get(horizon)
                excess[horizon] = round(own - mkt, 6) if own is not None and mkt is not None else None
            records.append(ForwardReturnRecord(
                run_date=run_date,
                symbol=symbol,
                candidate_score=score_map.get("candidate_score"),
                trade_readiness_score=score_map.get("trade_readiness_score"),
                price_setup_score=score_map.get("price_setup_score"),
                returns=returns,
                components=dict(score_map.get("components") or {}),
                excess=excess,
            ))
    return records


HEADLINE_SCORE_FIELDS = ("candidate_score", "trade_readiness_score", "price_setup_score")


def score_value(record: ForwardReturnRecord, field: str) -> float | None:
    """Resolve a score for `field` from either a headline attribute (candidate_score / …) or the
    record's `components` dict. This is what makes calibration factor-agnostic: any component or
    factor that lands in `components` can be bucketed / IC'd by name without new code."""
    if field in HEADLINE_SCORE_FIELDS:
        return getattr(record, field)
    return record.components.get(field)


def bucket_returns(
    records: list[ForwardReturnRecord],
    *,
    score_field: str,
    horizon: int,
    n_buckets: int = 5,
) -> list[dict[str, Any]]:
    """Bucket records into `n_buckets` quantiles by `score_field` and report, per bucket, the
    sample count, mean forward return, mean excess return over the benchmark, and hit rate
    (fraction with positive return) at `horizon`. Bucket monotonicity (higher score → higher mean
    return) is the headline signal-quality check; the excess column shows whether that monotonicity
    survives once the market move is stripped out. Records missing the score or the horizon return
    are skipped."""
    usable = [
        (score_value(rec, score_field), rec.returns.get(horizon), rec.excess.get(horizon))
        for rec in records
        if score_value(rec, score_field) is not None and rec.returns.get(horizon) is not None
    ]
    if not usable:
        return []
    usable.sort(key=lambda item: item[0])
    n = len(usable)
    n_buckets = max(1, min(n_buckets, n))
    buckets: list[dict[str, Any]] = []
    for b in range(n_buckets):
        lo = b * n // n_buckets
        hi = (b + 1) * n // n_buckets if b < n_buckets - 1 else n
        chunk = usable[lo:hi]
        if not chunk:
            continue
        scores = [score for score, _, _ in chunk]
        rets = [ret for _, ret, _ in chunk]
        excess = [exc for _, _, exc in chunk if exc is not None]
        buckets.append({
            "bucket": b + 1,
            "count": len(chunk),
            "score_min": round(min(scores), 2),
            "score_max": round(max(scores), 2),
            "mean_return": round(sum(rets) / len(rets), 6),
            "mean_excess_return": round(sum(excess) / len(excess), 6) if excess else None,
            "hit_rate": round(sum(1 for r in rets if r > 0) / len(rets), 4),
        })
    return buckets
