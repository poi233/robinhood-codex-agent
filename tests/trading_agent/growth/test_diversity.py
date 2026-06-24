import json
from pathlib import Path

from trading_agent.core.context import build_experiment_runtime_paths, build_runtime_paths
from trading_agent.growth.diversity import (
    CHAMPION_KEY,
    _daily_equity_returns,
    build_diversity_report,
    greedy_diverse_selection,
    jaccard_overlap,
    pairwise_return_correlation,
)
from trading_agent.growth.evaluator import _recommendation


def test_daily_equity_returns_collapses_to_last_per_day():
    rows = [
        {"timestamp": "2026-06-10T06:30:00", "total_equity": 1000.0},
        {"timestamp": "2026-06-10T13:00:00", "total_equity": 1010.0},  # last wins for the day
        {"timestamp": "2026-06-11T13:00:00", "total_equity": 1111.0},
    ]
    returns = _daily_equity_returns(rows)
    assert set(returns) == {"2026-06-11"}  # first day has no prior, so no return
    assert round(returns["2026-06-11"], 4) == round(1111.0 / 1010.0 - 1, 4)


def test_pairwise_correlation_detects_anti_correlation():
    a = {"d1": 0.10, "d2": -0.05, "d3": 0.10, "d4": -0.05}
    b = {"d1": -0.10, "d2": 0.05, "d3": -0.10, "d4": 0.05}
    matrix = pairwise_return_correlation({"A": a, "B": b})
    assert matrix["A"]["A"] == 1.0
    assert matrix["A"]["B"] is not None and matrix["A"]["B"] < -0.9


def test_correlation_is_none_under_three_common_days():
    a = {"d1": 0.1, "d2": 0.2}
    b = {"d1": -0.1, "d2": -0.2}
    matrix = pairwise_return_correlation({"A": a, "B": b})
    assert matrix["A"]["B"] is None


def test_jaccard_overlap_of_entry_sets():
    entry_sets = {
        "A": {("2026-06-10", "NVDA"), ("2026-06-11", "AMD")},
        "B": {("2026-06-10", "NVDA")},
    }
    overlap = jaccard_overlap(entry_sets)
    assert overlap["A"]["B"] == 0.5  # 1 shared / 2 union


def test_greedy_selection_picks_best_edge_then_excludes_correlated():
    edge = {"A": 100.0, "B": 90.0, "C": 80.0}
    corr = {
        "A": {"A": 1.0, "B": 0.95, "C": 0.1},
        "B": {"A": 0.95, "B": 1.0, "C": 0.2},
        "C": {"A": 0.1, "C": 1.0, "B": 0.2},
    }
    # A is best; B is too correlated to A (0.95 > 0.7) so dropped; C is diverse → kept.
    assert greedy_diverse_selection(edge, corr, max_corr=0.7) == ["A", "C"]


def test_greedy_selection_skips_none_or_negative_edge():
    edge = {"A": 50.0, "B": None, "C": -10.0}
    corr = {"A": {"A": 1.0}}
    assert greedy_diverse_selection(edge, corr, max_corr=0.7, min_edge=0.0) == ["A"]


def _write_equity(path: Path, day: str, equity: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"timestamp": f"{day}T13:00:00", "total_equity": equity}) + "\n")


def test_build_diversity_report_end_to_end(tmp_path):
    run_dates = ["2026-06-10", "2026-06-11", "2026-06-12", "2026-06-15"]
    a_equity = {"2026-06-10": 1000.0, "2026-06-11": 1100.0, "2026-06-12": 1050.0, "2026-06-15": 1200.0}
    b_equity = {"2026-06-10": 1000.0, "2026-06-11": 900.0, "2026-06-12": 950.0, "2026-06-15": 850.0}
    for rd in run_dates:
        _write_equity(build_experiment_runtime_paths(tmp_path, run_date=rd, strategy_id="A").paper_equity_curve_path, rd, a_equity[rd])
        _write_equity(build_experiment_runtime_paths(tmp_path, run_date=rd, strategy_id="B").paper_equity_curve_path, rd, b_equity[rd])
        _write_equity(build_runtime_paths(tmp_path, run_date=rd).paper_equity_curve_path, rd, 1000.0 + 1.0)  # champion ~flat

    decisions = {
        "A": [{"run_date": "2026-06-10", "decision": "would_trade", "symbol": "NVDA"}],
        "B": [{"run_date": "2026-06-10", "decision": "would_trade", "symbol": "NVDA"}],
    }
    report = build_diversity_report(
        tmp_path,
        run_dates=run_dates,
        challenger_ids=["A", "B"],
        decisions_by_strategy=decisions,
        edge_by_id={"A": 200.0, "B": -150.0},
    )
    corr = report["return_correlation"]
    assert corr["A"]["B"] is not None and corr["A"]["B"] < 0  # A up-ish, B down-ish
    assert CHAMPION_KEY in corr  # champion folded into the matrix
    assert report["entry_overlap"]["A"]["B"] == 1.0  # both entered NVDA on the same day
    assert report["diverse_selection"] == ["A"]  # only A has positive edge


def test_min_filled_trades_gate():
    champion = {"fill_rate_pct": 0.0, "max_drawdown": 0.0}
    small = {"shadow_days": 99, "filled": 3, "fill_rate_pct": 100.0, "max_drawdown": 0.0}
    rec = _recommendation(small, champion, {"min_filled_trades": 20})
    assert rec["recommend_promote"] is False
    assert any("min_filled_trades" in r for r in rec["blocking_reasons"])

    enough = {**small, "filled": 25}
    rec2 = _recommendation(enough, champion, {"min_filled_trades": 20})
    assert all("min_filled_trades" not in r for r in rec2["blocking_reasons"])

    off = {**small, "filled": 0}
    rec3 = _recommendation(off, champion, {})  # gate default off
    assert all("min_filled_trades" not in r for r in rec3["blocking_reasons"])
