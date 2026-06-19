from __future__ import annotations

import json
from pathlib import Path

from trading_agent.core.io import read_json
from trading_agent.screener.factor_gate import CandidateEvaluation
from trading_agent.screener.universe_update import (
    apply_universe_update,
    plan_universe_update,
    write_audit,
)


def _ev(symbol: str, score: float | None, *, passed: bool = True, reason: str | None = None) -> CandidateEvaluation:
    return CandidateEvaluation(
        symbol=symbol,
        factor_score=score,
        passed_gate=passed,
        reject_reason=reason,
        data_quality="ok",
        last_close=100.0,
        avg_dollar_volume=50_000_000.0,
        ret_20d=1.0,
        ret_60d=1.0,
        rel_strength_20d=1.0,
        above_sma50=True,
        above_sma200=True,
    )


def test_add_only_rate_limited_top_scores_win():
    discovered = [{"symbol": "A", "theme": "x"}, {"symbol": "B"}, {"symbol": "C"}]
    evals = {"A": _ev("A", 9.0), "B": _ev("B", 5.0), "C": _ev("C", 7.0)}
    plan = plan_universe_update(
        existing_symbols=["NVDA"],
        existing_meta={"NVDA": {"tier": "active"}},
        evaluations=evals,
        discovered=discovered,
        max_adds_per_week=2,
        universe_max=120,
        protected={"NVDA"},
    )
    # top 2 by score: A(9) and C(7); B rate-limited
    assert plan.added_symbols == ["A", "C"]
    reasons = {s["symbol"]: s["reason"] for s in plan.skipped}
    assert reasons["B"] == "rate_limited"


def test_gate_failed_and_existing_are_skipped():
    discovered = [{"symbol": "BAD"}, {"symbol": "NVDA"}]
    evals = {"BAD": _ev("BAD", None, passed=False, reason="not_in_uptrend")}
    plan = plan_universe_update(
        existing_symbols=["NVDA"],
        existing_meta={},
        evaluations=evals,
        discovered=discovered,
        max_adds_per_week=5,
        universe_max=120,
        protected=set(),
    )
    assert plan.added_symbols == []
    reasons = {s["symbol"]: s["reason"] for s in plan.skipped}
    assert reasons["BAD"] == "not_in_uptrend"
    assert reasons["NVDA"] == "already_in_universe"


def test_rerank_writes_scores_for_all_scored():
    evals = {"NVDA": _ev("NVDA", 8.0), "AMD": _ev("AMD", 3.0)}
    plan = plan_universe_update(
        existing_symbols=["NVDA", "AMD"],
        existing_meta={},
        evaluations=evals,
        discovered=[],
        max_adds_per_week=5,
        universe_max=120,
        protected=set(),
    )
    assert plan.meta_score_updates["NVDA"]["screen_rank"] == 1
    assert plan.meta_score_updates["AMD"]["screen_rank"] == 2
    assert plan.meta_score_updates["NVDA"]["screen_score"] == 8.0


def test_cap_demote_lowest_nonprotected_watch():
    existing = ["SPY", "HIGH", "MID", "LOW"]
    meta = {
        "SPY": {"tier": "active"},
        "HIGH": {"tier": "watch"},
        "MID": {"tier": "watch"},
        "LOW": {"tier": "watch"},
    }
    evals = {
        "SPY": _ev("SPY", 1.0),
        "HIGH": _ev("HIGH", 9.0),
        "MID": _ev("MID", 5.0),
        "LOW": _ev("LOW", 1.0),
    }
    plan = plan_universe_update(
        existing_symbols=existing,
        existing_meta=meta,
        evaluations=evals,
        discovered=[],
        max_adds_per_week=5,
        universe_max=3,  # effective is 4 → must demote 1
        protected={"SPY"},
    )
    # LOW has the worst score among non-protected watch → demoted; SPY protected.
    assert plan.demoted == ["LOW"]
    assert plan.effective_count_after == 3


def test_protected_never_demoted_even_if_lowest():
    existing = ["SPY", "A", "B"]
    meta = {"SPY": {"tier": "watch"}, "A": {"tier": "watch"}, "B": {"tier": "watch"}}
    evals = {"SPY": _ev("SPY", -99.0), "A": _ev("A", 5.0), "B": _ev("B", 6.0)}
    plan = plan_universe_update(
        existing_symbols=existing,
        existing_meta=meta,
        evaluations=evals,
        discovered=[],
        max_adds_per_week=5,
        universe_max=2,
        protected={"SPY"},
    )
    assert "SPY" not in plan.demoted
    assert plan.demoted == ["A"]  # worst non-protected


def _seed_config(root: Path) -> Path:
    config_dir = root / "src" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "universe.txt").write_text("# header\nNVDA\nAMD\n", encoding="utf-8")
    (config_dir / "universe_meta.json").write_text(
        json.dumps({"_comment": "meta", "NVDA": {"tier": "active"}, "AMD": {"tier": "watch"}}),
        encoding="utf-8",
    )
    return config_dir


def test_apply_appends_universe_and_updates_meta(tmp_path):
    config_dir = _seed_config(tmp_path)
    run_dir = tmp_path / "runtime" / "screener" / "2026-06-21"
    evals = {"NVDA": _ev("NVDA", 8.0), "AMD": _ev("AMD", 2.0), "SIVE": _ev("SIVE", 9.0)}
    plan = plan_universe_update(
        existing_symbols=["NVDA", "AMD"],
        existing_meta={"NVDA": {"tier": "active"}, "AMD": {"tier": "watch"}},
        evaluations=evals,
        discovered=[{"symbol": "SIVE", "theme": "photonics", "thesis": "laser chokepoint"}],
        max_adds_per_week=5,
        universe_max=120,
        protected={"NVDA"},
    )
    result = apply_universe_update(config_dir=config_dir, run_dir=run_dir, run_date="2026-06-21", plan=plan)

    universe_text = (config_dir / "universe.txt").read_text(encoding="utf-8")
    assert "NVDA" in universe_text and "AMD" in universe_text  # nothing deleted
    assert universe_text.index("NVDA") < universe_text.index("SIVE")  # appended after, not reordered
    assert "Added by weekly screener 2026-06-21" in universe_text

    meta = read_json(config_dir / "universe_meta.json")
    assert meta["SIVE"]["tier"] == "watch"
    assert meta["SIVE"]["source"] == "serenity_screen"
    assert meta["SIVE"]["screen_rank"] == 1  # highest score
    assert meta["NVDA"]["screen_score"] == 8.0
    assert (run_dir / "backup" / "universe.txt").exists()
    assert result["added"] == ["SIVE"]


def test_apply_demotion_sets_passive_keeps_in_file(tmp_path):
    config_dir = _seed_config(tmp_path)
    run_dir = tmp_path / "runtime" / "screener" / "2026-06-21"
    # force AMD demotion via tiny cap
    evals = {"NVDA": _ev("NVDA", 8.0), "AMD": _ev("AMD", 1.0)}
    plan = plan_universe_update(
        existing_symbols=["NVDA", "AMD"],
        existing_meta={"NVDA": {"tier": "active"}, "AMD": {"tier": "watch"}},
        evaluations=evals,
        discovered=[],
        max_adds_per_week=5,
        universe_max=1,
        protected={"NVDA"},
    )
    assert plan.demoted == ["AMD"]
    apply_universe_update(config_dir=config_dir, run_dir=run_dir, run_date="2026-06-21", plan=plan)
    meta = read_json(config_dir / "universe_meta.json")
    assert meta["AMD"]["tier"] == "passive"
    assert "AMD" in (config_dir / "universe.txt").read_text(encoding="utf-8")  # still in file


def test_write_audit_emits_json_and_md(tmp_path):
    run_dir = tmp_path / "screener"
    evals = {"SIVE": _ev("SIVE", 9.0)}
    plan = plan_universe_update(
        existing_symbols=[],
        existing_meta={},
        evaluations=evals,
        discovered=[{"symbol": "SIVE", "theme": "photonics", "thesis": "laser"}],
        max_adds_per_week=5,
        universe_max=120,
        protected=set(),
    )
    json_path, md_path = write_audit(run_dir=run_dir, run_date="2026-06-21", plan=plan, applied=True)
    assert json.loads(json_path.read_text(encoding="utf-8"))["added"][0]["symbol"] == "SIVE"
    assert "Weekly universe change" in md_path.read_text(encoding="utf-8")
