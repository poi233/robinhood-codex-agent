from __future__ import annotations

import json
from pathlib import Path

from trading_agent.core.io import write_json
from trading_agent.replay.benchmark_returns import compute_benchmark_returns
from trading_agent.replay.component_attribution import component_attribution
from trading_agent.replay.forward_returns import ForwardReturnRecord
from trading_agent.replay.setup_outcomes import setup_outcomes


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


# --- benchmark returns ---

def test_benchmark_returns_per_horizon(tmp_path):
    (tmp_path / "runtime" / "state" / "runs" / "2026-06-15").mkdir(parents=True)

    def loader(symbol, start, end):
        return {"SPY": [("2026-06-15", 100.0), ("2026-06-16", 101.0), ("2026-06-18", 103.0)]}.get(symbol, [])

    out = compute_benchmark_returns(tmp_path, horizons=(1,), benchmarks=("SPY",), price_loader=loader)
    assert out["SPY"][1]["mean_return"] == round(101.0 / 100.0 - 1, 6)
    assert out["SPY"][1]["count"] == 1


# --- component attribution (IC) ---

def test_component_attribution_ranks_by_information_coefficient():
    # technical perfectly predicts return; kronos is pure noise (constant).
    records = []
    for i in range(1, 11):
        records.append(ForwardReturnRecord(
            "d", f"S{i}", candidate_score=float(i), trade_readiness_score=None, price_setup_score=None,
            returns={1: 0.01 * i}, components={"technical": float(i), "kronos": 5.0}))
    rows = component_attribution(records, horizon=1)
    by_name = {r["component"]: r for r in rows}
    assert round(by_name["technical"]["ic"], 3) == 1.0      # perfectly monotonic
    assert by_name["kronos"]["ic"] is None                  # zero variance => undefined
    # candidate_score is also attributed (it equals i here)
    assert round(by_name["candidate_score"]["ic"], 3) == 1.0
    # ranked by |ic| desc, undefined last
    assert rows[0]["component"] in {"technical", "candidate_score"}


# --- setup outcomes ---

def _seed_orders_and_levels(agent_root: Path, run_date: str) -> None:
    run_dir = agent_root / "runtime" / "state" / "runs" / run_date
    paper = run_dir / "paper"
    _write_jsonl(paper / "orders.jsonl", [
        {"order_id": "o1", "symbol": "NVDA", "side": "buy", "status": "filled", "fill_price": 100.0,
         "setup_type": "breakout", "stop_price": 95.0, "target_1": 110.0, "timestamp": f"{run_date}T09:31:00"},
        {"order_id": "o2", "symbol": "MU", "side": "buy", "status": "filled", "fill_price": 50.0,
         "setup_type": "pullback", "stop_price": 48.0, "target_1": 55.0, "timestamp": f"{run_date}T09:32:00"},
    ])


def test_setup_outcomes_target_before_stop(tmp_path):
    _seed_orders_and_levels(tmp_path, "2026-06-15")

    def loader(symbol, start, end):
        return {
            # NVDA hits target_1 (110) before stop (95)
            "NVDA": [("2026-06-15", 100.0), ("2026-06-16", 108.0), ("2026-06-17", 112.0)],
            # MU hits stop (48) before target (55)
            "MU": [("2026-06-15", 50.0), ("2026-06-16", 49.0), ("2026-06-17", 47.0)],
        }.get(symbol, [])

    out = setup_outcomes(tmp_path, lookahead=5, price_loader=loader)
    by_setup = {r["setup_type"]: r for r in out}
    assert by_setup["breakout"]["target_first"] == 1
    assert by_setup["breakout"]["stop_first"] == 0
    assert by_setup["pullback"]["stop_first"] == 1
    assert by_setup["pullback"]["target_first"] == 0
