from __future__ import annotations

import json
from pathlib import Path

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import write_json
from trading_agent.replay.ai_ablation import (
    _composite_ai_score,
    ai_ablation_report,
    format_ai_ablation_markdown,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _seed_candidate(agent_root: Path, run_date: str, symbol: str, score: float) -> None:
    # Merge into the existing candidate_scores.json so seeding several symbols for one run date does
    # not overwrite earlier ones.
    path = agent_root / "runtime" / "state" / "runs" / run_date / "planner" / "candidate_scores.json"
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"symbols": {}}
    existing.setdefault("symbols", {})[symbol] = {
        "score": score, "total_score": score, "score_status": "scored", "components": {}}
    write_json(path, existing)


def _env(layer: str, symbol: str, run_date: str, direction: str, confidence: float) -> dict:
    return {"layer": layer, "symbol": symbol, "asof_date": run_date, "direction": direction,
            "confidence": confidence, "reason_codes": [], "warning_codes": []}


def _seed_ai(agent_root: Path, run_date: str, envs: list[dict]) -> None:
    paths = build_runtime_paths(agent_root, run_date=run_date)
    layers: dict[str, list] = {"dsa": [], "kronos": [], "catalyst": []}
    for e in envs:
        layers.setdefault(e["layer"], []).append(e)
    write_json(paths.ai_signals_path, {"date": run_date, "asof_date": run_date, "layers": layers})


def _loader(series):
    def loader(symbol, start, end):
        return series.get(symbol, [])
    return loader


def test_composite_score_signs_by_direction():
    assert _composite_ai_score([{"direction": "long", "confidence": 0.8}]) == 0.8
    assert _composite_ai_score([{"direction": "short", "confidence": 0.5}]) == -0.5
    assert _composite_ai_score([{"direction": "neutral", "confidence": 0.9}]) == 0.0


def test_ablation_collapses_when_only_informative_layer_is_dropped(tmp_path):
    # One consistent rising/falling timeline per symbol. Kronos is the only directional layer (long
    # WIN, short LOSE); dsa is uniform-neutral (no variance). Dropping kronos removes all conviction,
    # so the combined score has zero variance and its IC becomes undefined (None) — the clearest
    # signal that kronos is load-bearing.
    series = {
        "WIN": [("2026-06-15", 100.0), ("2026-06-16", 110.0), ("2026-06-17", 121.0)],
        "LOSE": [("2026-06-15", 100.0), ("2026-06-16", 95.0), ("2026-06-17", 90.25)],
        "SPY": [("2026-06-15", 400.0), ("2026-06-16", 401.0), ("2026-06-17", 402.0)],
    }
    for rd in ("2026-06-15", "2026-06-16"):
        for sym in ("WIN", "LOSE"):
            _seed_candidate(tmp_path, rd, sym, 70.0)
        _seed_ai(tmp_path, rd, [
            _env("kronos", "WIN", rd, "long", 0.9),
            _env("kronos", "LOSE", rd, "short", 0.9),
            _env("dsa", "WIN", rd, "neutral", 0.5),
            _env("dsa", "LOSE", rd, "neutral", 0.5),
        ])

    report = ai_ablation_report(tmp_path, horizons=(1,), price_loader=_loader(series))

    variants = report["variants"]
    assert variants["full_ai"]["n"] == 4
    assert variants["full_ai"]["ic"] is not None         # kronos gives the score real variance
    assert variants["drop_kronos"]["ic"] is None          # without it, every score is 0 -> undefined
    assert variants["drop_dsa"]["ic"] is not None          # dsa was noise; dropping it keeps the signal


def test_ablation_empty_when_no_signals(tmp_path):
    report = ai_ablation_report(tmp_path, horizons=(1,), price_loader=_loader({}))
    assert report["matched_symbol_runs"] == 0
    md = format_ai_ablation_markdown(report)
    assert "AI Layer Ablation" in md
