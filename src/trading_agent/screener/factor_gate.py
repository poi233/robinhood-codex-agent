from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from trading_agent.planner.technical_features import pct_return, sma
from trading_agent.screener.config import ScreenerConfig
from trading_agent.signals.dsa_metrics import Downloader, default_downloader

# A symbol needs at least this many daily bars before we trust its factor read.
MIN_BARS_OK = 60
# Lookback wide enough to compute SMA200 (≈200 trading days) plus headroom.
DEFAULT_LOOKBACK_DAYS = 400
# Factor-score weights (transparent, deterministic; used to RANK candidates).
W_REL_STRENGTH_20D = 0.40
W_RET_60D = 0.30
W_ABOVE_SMA50 = 0.15
W_ABOVE_SMA200 = 0.15
_TREND_POINTS = 5.0


@dataclass(frozen=True)
class CandidateEvaluation:
    """One symbol's factor read + strict-gate verdict.

    ``passed_gate`` is what O1's auto-apply writer uses to decide eligibility for *new* adds;
    ``factor_score`` is the ranking key for both new adds and the universe-wide re-rank.
    """

    symbol: str
    factor_score: float | None
    passed_gate: bool
    reject_reason: str | None
    data_quality: str
    last_close: float | None
    avg_dollar_volume: float | None
    ret_20d: float | None
    ret_60d: float | None
    rel_strength_20d: float | None
    above_sma50: bool | None
    above_sma200: bool | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _avg_dollar_volume(closes: list[float], volumes: list[float], window: int = 20) -> float | None:
    if not closes or not volumes:
        return None
    n = min(len(closes), len(volumes), window)
    if n <= 0:
        return None
    recent_close = closes[-n:]
    recent_vol = volumes[-n:]
    return sum(c * v for c, v in zip(recent_close, recent_vol)) / n


def compute_factor_score(
    *,
    rel_strength_20d: float | None,
    ret_60d: float | None,
    above_sma50: bool | None,
    above_sma200: bool | None,
) -> float:
    """Transparent momentum/trend blend. Missing momentum terms contribute 0; an unknown
    trend (None) counts as below (conservative)."""
    score = 0.0
    if rel_strength_20d is not None:
        score += W_REL_STRENGTH_20D * rel_strength_20d
    if ret_60d is not None:
        score += W_RET_60D * ret_60d
    score += W_ABOVE_SMA50 * (_TREND_POINTS if above_sma50 else -_TREND_POINTS)
    score += W_ABOVE_SMA200 * (_TREND_POINTS if above_sma200 else -_TREND_POINTS)
    return round(score, 4)


def evaluate_candidate(
    symbol: str,
    rows: list[dict[str, Any]] | None,
    benchmark_closes: list[float] | None,
    config: ScreenerConfig,
) -> CandidateEvaluation:
    """Compute factors for one symbol and apply the strict gate (data → liquidity → trend)."""
    if not rows:
        return CandidateEvaluation(
            symbol=symbol,
            factor_score=None,
            passed_gate=False,
            reject_reason="no_data",
            data_quality="failed",
            last_close=None,
            avg_dollar_volume=None,
            ret_20d=None,
            ret_60d=None,
            rel_strength_20d=None,
            above_sma50=None,
            above_sma200=None,
        )

    rows_sorted = sorted(rows, key=lambda r: r["date"])
    closes = [float(r["close"]) for r in rows_sorted]
    volumes = [float(r.get("volume") or 0) for r in rows_sorted]
    last_close = closes[-1]

    if len(closes) >= MIN_BARS_OK:
        data_quality = "ok"
    elif len(closes) >= 20:
        data_quality = "partial"
    else:
        data_quality = "failed"

    sma50 = sma(closes, 50)
    sma200 = sma(closes, 200)
    above_sma50 = bool(sma50 is not None and last_close >= sma50)
    above_sma200 = bool(last_close >= sma200) if sma200 is not None else None

    ret_20d = pct_return(closes, 20)
    ret_60d = pct_return(closes, 60)
    rel_strength_20d: float | None = None
    if benchmark_closes:
        bench_20d = pct_return(benchmark_closes, 20)
        if ret_20d is not None and bench_20d is not None:
            rel_strength_20d = round(ret_20d - bench_20d, 4)

    avg_dollar_volume = _avg_dollar_volume(closes, volumes)
    factor_score = compute_factor_score(
        rel_strength_20d=rel_strength_20d,
        ret_60d=ret_60d,
        above_sma50=above_sma50,
        above_sma200=above_sma200,
    )

    # Strict gate, fail-closed and ordered: insufficient data → thin liquidity → no uptrend.
    reject_reason: str | None = None
    if data_quality != "ok":
        reject_reason = "insufficient_data"
    elif avg_dollar_volume is None or avg_dollar_volume < config.min_dollar_volume:
        reject_reason = "below_min_dollar_volume"
    elif config.require_uptrend and above_sma200 is not True:
        reject_reason = "not_in_uptrend"

    return CandidateEvaluation(
        symbol=symbol,
        factor_score=factor_score,
        passed_gate=reject_reason is None,
        reject_reason=reject_reason,
        data_quality=data_quality,
        last_close=round(last_close, 4),
        avg_dollar_volume=round(avg_dollar_volume, 2) if avg_dollar_volume is not None else None,
        ret_20d=round(ret_20d, 2) if ret_20d is not None else None,
        ret_60d=round(ret_60d, 2) if ret_60d is not None else None,
        rel_strength_20d=rel_strength_20d,
        above_sma50=above_sma50,
        above_sma200=above_sma200,
    )


def validate_candidates(
    symbols: list[str],
    *,
    config: ScreenerConfig,
    run_date: str,
    downloader: Downloader | None = None,
    benchmark: str = "SPY",
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> list[CandidateEvaluation]:
    """Download OHLCV once for ``symbols`` (+ benchmark) and evaluate each with the strict gate.

    Pure aside from the injected ``downloader`` (defaults to yfinance via
    ``dsa_metrics.default_downloader``); tests pass a synthetic downloader for full offline
    coverage. Download failure → every symbol comes back ``no_data`` (fail-closed), never raises.
    """
    deduped = list(dict.fromkeys(s.upper() for s in symbols if s))
    if not deduped:
        return []

    active_downloader = downloader or default_downloader
    tickers = sorted(set(deduped) | {benchmark})
    try:
        raw = active_downloader(tickers, lookback_days, run_date)
    except Exception:
        raw = {}

    bench_rows = raw.get(benchmark)
    benchmark_closes: list[float] | None = None
    if bench_rows:
        benchmark_closes = [float(r["close"]) for r in sorted(bench_rows, key=lambda r: r["date"])]

    return [evaluate_candidate(sym, raw.get(sym), benchmark_closes, config) for sym in deduped]
