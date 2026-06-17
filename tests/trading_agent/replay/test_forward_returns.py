from __future__ import annotations

from pathlib import Path

from trading_agent.core.io import write_json
from trading_agent.replay.forward_returns import (
    ForwardReturnRecord,
    bucket_returns,
    compute_forward_return_records,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    import json
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _seed_run(agent_root: Path, run_date: str, *, candidate_score: float, trade_readiness: float, price_setup: float) -> None:
    run_dir = agent_root / "runtime" / "state" / "runs" / run_date
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json(run_dir / "planner" / "candidate_scores.json", {"symbols": {
        "NVDA": {"score": candidate_score, "total_score": candidate_score, "score_status": "scored", "components": {}}}})
    _write_jsonl(agent_root / "runtime" / "logs" / "runs" / run_date / "audit" / "intraday_rankings.jsonl", [
        {"timestamp": f"{run_date}T09:31:00", "run_date": run_date, "symbol": "NVDA",
         "trade_readiness_score": trade_readiness, "price_setup_score": price_setup}])


def _fake_loader(series: dict[str, list[tuple[str, float]]]):
    def loader(symbol: str, start: str, end: str) -> list[tuple[str, float]]:
        return series.get(symbol, [])
    return loader


def test_forward_returns_computed_per_horizon(tmp_path):
    _seed_run(tmp_path, "2026-06-15", candidate_score=66.0, trade_readiness=72.0, price_setup=70.0)
    loader = _fake_loader({"NVDA": [
        ("2026-06-15", 100.0), ("2026-06-16", 101.0), ("2026-06-17", 103.0),
        ("2026-06-18", 102.0), ("2026-06-19", 105.0), ("2026-06-22", 110.0)]})

    records = compute_forward_return_records(tmp_path, horizons=(1, 3, 5), price_loader=loader)

    assert len(records) == 1
    rec = records[0]
    assert rec.symbol == "NVDA"
    assert rec.candidate_score == 66.0
    assert rec.trade_readiness_score == 72.0
    assert rec.price_setup_score == 70.0
    assert rec.returns[1] == round(101.0 / 100.0 - 1, 6)   # +1%
    assert rec.returns[3] == round(102.0 / 100.0 - 1, 6)   # 3 trading days later
    assert rec.returns[5] == round(110.0 / 100.0 - 1, 6)   # 5 trading days later


def test_forward_return_is_none_when_not_enough_future_bars(tmp_path):
    _seed_run(tmp_path, "2026-06-15", candidate_score=66.0, trade_readiness=72.0, price_setup=70.0)
    loader = _fake_loader({"NVDA": [("2026-06-15", 100.0), ("2026-06-16", 101.0)]})

    records = compute_forward_return_records(tmp_path, horizons=(1, 3, 5), price_loader=loader)

    assert records[0].returns[1] == round(101.0 / 100.0 - 1, 6)
    assert records[0].returns[3] is None  # only one future bar
    assert records[0].returns[5] is None


def test_entry_uses_first_bar_on_or_after_run_date(tmp_path):
    # run_date is a weekend/holiday with no bar; entry falls to the next session.
    _seed_run(tmp_path, "2026-06-13", candidate_score=50.0, trade_readiness=60.0, price_setup=55.0)
    loader = _fake_loader({"NVDA": [("2026-06-15", 200.0), ("2026-06-16", 210.0)]})

    records = compute_forward_return_records(tmp_path, horizons=(1,), price_loader=loader)
    assert records[0].returns[1] == round(210.0 / 200.0 - 1, 6)


def test_bucket_returns_groups_by_score_quantile_with_hit_rate():
    records = [
        ForwardReturnRecord("d", f"S{i}", candidate_score=float(i), trade_readiness_score=None,
                            price_setup_score=None, returns={1: (0.01 * (i - 2))})
        for i in range(1, 11)  # scores 1..10, returns -0.01..+0.08
    ]
    buckets = bucket_returns(records, score_field="candidate_score", horizon=1, n_buckets=2)
    assert len(buckets) == 2
    low, high = buckets
    assert low["count"] == 5 and high["count"] == 5
    # higher score bucket should have higher mean forward return (monotonic signal)
    assert high["mean_return"] > low["mean_return"]
    assert 0.0 <= low["hit_rate"] <= 1.0 and 0.0 <= high["hit_rate"] <= 1.0


def test_bucket_returns_skips_missing_scores_and_returns():
    records = [
        ForwardReturnRecord("d", "A", candidate_score=None, trade_readiness_score=None, price_setup_score=None, returns={1: 0.05}),
        ForwardReturnRecord("d", "B", candidate_score=5.0, trade_readiness_score=None, price_setup_score=None, returns={1: None}),
        ForwardReturnRecord("d", "C", candidate_score=7.0, trade_readiness_score=None, price_setup_score=None, returns={1: 0.02}),
    ]
    buckets = bucket_returns(records, score_field="candidate_score", horizon=1, n_buckets=1)
    assert sum(b["count"] for b in buckets) == 1  # only C is usable


def test_bucket_returns_works_for_component_fields():
    from trading_agent.replay.forward_returns import score_value
    records = [
        ForwardReturnRecord("d", f"S{i}", candidate_score=None, trade_readiness_score=None,
                            price_setup_score=None, returns={1: 0.01 * i}, components={"factor_alpha": float(i)})
        for i in range(1, 11)
    ]
    # score_value resolves component keys, not just headline attributes.
    assert score_value(records[0], "factor_alpha") == 1.0
    assert score_value(records[0], "candidate_score") is None
    buckets = bucket_returns(records, score_field="factor_alpha", horizon=1, n_buckets=2)
    assert len(buckets) == 2
    assert buckets[1]["mean_return"] > buckets[0]["mean_return"]  # higher factor -> higher return


def test_excess_return_subtracts_benchmark(tmp_path):
    _seed_run(tmp_path, "2026-06-15", candidate_score=66.0, trade_readiness=72.0, price_setup=70.0)
    loader = _fake_loader({
        "NVDA": [("2026-06-15", 100.0), ("2026-06-16", 110.0)],   # +10% at 1d
        "SPY":  [("2026-06-15", 400.0), ("2026-06-16", 412.0)],   # +3% at 1d
    })
    records = compute_forward_return_records(tmp_path, horizons=(1,), price_loader=loader, benchmark="SPY")
    rec = records[0]
    assert rec.returns[1] == round(110.0 / 100.0 - 1, 6)
    assert rec.excess[1] == round((110.0 / 100.0 - 1) - (412.0 / 400.0 - 1), 6)  # 10% - 3% = 7%


def test_excess_is_none_when_benchmark_return_pending(tmp_path):
    _seed_run(tmp_path, "2026-06-15", candidate_score=66.0, trade_readiness=72.0, price_setup=70.0)
    loader = _fake_loader({
        "NVDA": [("2026-06-15", 100.0), ("2026-06-16", 110.0)],
        "SPY":  [("2026-06-15", 400.0)],  # no future bar -> benchmark 1d return is None
    })
    records = compute_forward_return_records(tmp_path, horizons=(1,), price_loader=loader, benchmark="SPY")
    assert records[0].returns[1] is not None
    assert records[0].excess[1] is None


def test_bucket_returns_reports_mean_excess():
    records = [
        ForwardReturnRecord("d", f"S{i}", candidate_score=float(i), trade_readiness_score=None,
                            price_setup_score=None, returns={1: 0.01 * i}, excess={1: 0.005 * i})
        for i in range(1, 11)
    ]
    buckets = bucket_returns(records, score_field="candidate_score", horizon=1, n_buckets=2)
    assert buckets[1]["mean_excess_return"] > buckets[0]["mean_excess_return"]


def test_component_ic_summary_reports_per_horizon_tstat():
    from trading_agent.replay.component_attribution import component_ic_summary
    # Two run dates; within each, factor_alpha perfectly ranks the 1d return -> per-date IC = 1.
    records = []
    for run_date in ("2026-06-15", "2026-06-16"):
        for i in range(1, 6):
            records.append(ForwardReturnRecord(
                run_date, f"S{i}", candidate_score=None, trade_readiness_score=None,
                price_setup_score=None, returns={1: 0.01 * i}, components={"factor_alpha": float(i)}))
    summary = component_ic_summary(records, horizons=(1,))
    top = next(r for r in summary if r["component"] == "factor_alpha")
    stats = top["horizons"]["1"]
    assert stats["periods"] == 2
    assert stats["mean_ic"] == 1.0
    assert stats["pooled_ic"] == 1.0
    # zero variance across dates (both ICs == 1) -> t-stat undefined, reported as None
    assert stats["t_stat"] is None
