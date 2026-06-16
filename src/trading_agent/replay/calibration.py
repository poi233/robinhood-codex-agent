from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_agent.core.io import write_json
from trading_agent.replay.analysis import discover_run_dates
from trading_agent.replay.benchmark_returns import DEFAULT_BENCHMARKS, compute_benchmark_returns
from trading_agent.replay.component_attribution import component_attribution
from trading_agent.replay.forward_returns import (
    DEFAULT_HORIZONS,
    PriceLoader,
    bucket_returns,
    compute_forward_return_records,
    default_price_loader,
)
from trading_agent.replay.setup_outcomes import setup_outcomes

_SCORE_FIELDS = ("candidate_score", "trade_readiness_score", "price_setup_score")


def build_calibration_report(
    agent_root: Path,
    *,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    benchmarks: tuple[str, ...] = DEFAULT_BENCHMARKS,
    since: str | None = None,
    until: str | None = None,
    n_buckets: int = 5,
    price_loader: PriceLoader = default_price_loader,
) -> dict[str, Any]:
    """Assemble the full E1 calibration report: score-bucket forward returns, component IC
    attribution, benchmark returns, and setup outcomes. Pure read + (real run) yfinance; the
    loader is injectable for tests. Does not write any trading parameter."""
    run_dates = discover_run_dates(agent_root, since_date=since, until_date=until)
    records = compute_forward_return_records(agent_root, horizons=horizons, since=since, until=until, price_loader=price_loader)

    score_buckets = {
        field: {str(h): bucket_returns(records, score_field=field, horizon=h, n_buckets=n_buckets) for h in horizons}
        for field in _SCORE_FIELDS
    }
    attribution = {str(h): component_attribution(records, horizon=h) for h in horizons}
    benchmark = compute_benchmark_returns(agent_root, horizons=horizons, benchmarks=benchmarks, since=since, until=until, price_loader=price_loader)
    setups = setup_outcomes(agent_root, since=since, until=until, price_loader=price_loader)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_date_count": len(run_dates),
        "sample_size": len(records),
        "horizons": list(horizons),
        "score_buckets": score_buckets,
        "attribution": {h: [dict(r) for r in rows] for h, rows in attribution.items()},
        "benchmarks": {sym: {str(h): v for h, v in per.items()} for sym, per in benchmark.items()},
        "setup_outcomes": setups,
    }


def default_calibration_report_path(agent_root: Path) -> Path:
    return agent_root / "runtime" / "analytics" / "calibration_report.json"


def default_calibration_md_path(agent_root: Path) -> Path:
    return agent_root / "runtime" / "analytics" / "calibration_report.md"


def _fmt_pct(value: Any) -> str:
    return f"{value * 100:+.2f}%" if isinstance(value, (int, float)) else "—"


def format_calibration_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Calibration Report",
        "",
        f"_Generated {report['generated_at']}._ Run dates: {report['run_date_count']} · "
        f"candidate samples: {report['sample_size']} · horizons (trading days): {report['horizons']}",
        "",
        "> Read-only analysis. Does not change any strategy parameter. Small samples are noisy — "
        "wait for 15–30 run dates before trusting bucket monotonicity or IC.",
        "",
    ]
    if report["sample_size"] == 0:
        lines.append("_No candidate samples with forward returns yet (need run dates with future price bars)._")
        return "\n".join(lines) + "\n"

    lines.append("## Score buckets vs forward return")
    lines.append("")
    for field, per_h in report["score_buckets"].items():
        for horizon, buckets in per_h.items():
            if not buckets:
                continue
            lines.append(f"**{field} · {horizon}d** (low → high score):")
            for b in buckets:
                lines.append(f"- bucket {b['bucket']} [{b['score_min']}–{b['score_max']}]  "
                             f"n={b['count']}  mean={_fmt_pct(b['mean_return'])}  hit={b['hit_rate'] * 100:.0f}%")
            lines.append("")

    lines.append("## Component attribution (Spearman IC, ranked)")
    lines.append("")
    for horizon, rows in report["attribution"].items():
        lines.append(f"**{horizon}d:** " + ", ".join(
            f"{r['component']}={r['ic']:.2f}(n{r['n']})" if r["ic"] is not None else f"{r['component']}=NA"
            for r in rows))
    lines.append("")

    lines.append("## Benchmark returns (separate alpha from beta)")
    lines.append("")
    for sym, per_h in report["benchmarks"].items():
        parts = [f"{h}d {_fmt_pct(v.get('mean_return'))}" for h, v in per_h.items()]
        lines.append(f"- {sym}: " + " · ".join(parts))
    lines.append("")

    lines.append("## Setup outcomes (target_1 before stop)")
    lines.append("")
    for row in report["setup_outcomes"]:
        wr = f"{row['win_rate'] * 100:.0f}%" if row["win_rate"] is not None else "—"
        lines.append(f"- {row['setup_type']}: fills={row['fills']}  target_first={row['target_first']}  "
                     f"stop_first={row['stop_first']}  win_rate={wr}")
    lines.append("")
    return "\n".join(lines) + "\n"


def write_calibration_report(
    agent_root: Path,
    *,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    benchmarks: tuple[str, ...] = DEFAULT_BENCHMARKS,
    since: str | None = None,
    until: str | None = None,
    n_buckets: int = 5,
    price_loader: PriceLoader = default_price_loader,
) -> tuple[Path, Path]:
    report = build_calibration_report(
        agent_root, horizons=horizons, benchmarks=benchmarks, since=since, until=until,
        n_buckets=n_buckets, price_loader=price_loader,
    )
    json_path = default_calibration_report_path(agent_root)
    md_path = default_calibration_md_path(agent_root)
    write_json(json_path, report)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(format_calibration_markdown(report), encoding="utf-8")
    return json_path, md_path
