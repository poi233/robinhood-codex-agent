import json
from pathlib import Path

from trading_agent.growth.observations import (
    build_growth_observations,
    default_growth_observations_path,
    write_growth_observations,
)


def _seed_run(agent_root: Path, run_date: str, *, decisions: list[dict], orders: list[dict], manifest: bool) -> None:
    run_dir = agent_root / "runtime" / "state" / "runs" / run_date
    paper = run_dir / "paper"
    paper.mkdir(parents=True, exist_ok=True)
    # decisions.jsonl lives under runtime/logs/runs/<date>/audit/ per RuntimePaths
    dec_dir = agent_root / "runtime" / "logs" / "runs" / run_date / "audit"
    dec_dir.mkdir(parents=True, exist_ok=True)
    with (dec_dir / "decisions.jsonl").open("w", encoding="utf-8") as fh:
        for row in decisions:
            fh.write(json.dumps(row) + "\n")
    with (paper / "orders.jsonl").open("w", encoding="utf-8") as fh:
        for row in orders:
            fh.write(json.dumps(row) + "\n")
    if manifest:
        (run_dir / "run_manifest.json").write_text(json.dumps({"strategy_id": "baseline_v1"}), encoding="utf-8")


def test_high_no_trade_rate_and_missing_manifest(tmp_path):
    # 5 no-trade decisions, all blocked by outside_entry_zone; no manifest.
    decisions = [
        {"timestamp": f"2026-06-15T07:0{i}:00-0700", "decision": "no_action",
         "blocked_reasons": ["outside_entry_zone"]}
        for i in range(5)
    ]
    _seed_run(tmp_path, "2026-06-15", decisions=decisions, orders=[], manifest=False)

    payload = build_growth_observations(tmp_path)
    types = {o["type"] for o in payload["global"]}
    assert "high_no_trade_rate" in types
    assert "dominant_blocked_reason" in types
    assert "missing_manifest" in types
    # modules key exists (filled in G2); empty/absent diagnosers are fine here.
    assert "modules" in payload


def test_write_growth_observations_is_read_only_artifact(tmp_path):
    _seed_run(tmp_path, "2026-06-15", decisions=[{"decision": "would_trade", "blocked_reasons": []}],
              orders=[], manifest=True)
    out = write_growth_observations(tmp_path)
    assert out == default_growth_observations_path(tmp_path)
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert "generated_at" in data and "global" in data
