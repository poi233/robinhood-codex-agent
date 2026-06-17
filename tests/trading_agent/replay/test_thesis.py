from __future__ import annotations

import json
from pathlib import Path

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import write_json
from trading_agent.replay.thesis import format_thesis_markdown, thesis_attribution, thesis_tags_for


def test_thesis_tags_combine_meta_and_dsa():
    tags = thesis_tags_for("NVDA",
                           {"primary_theme": "AI Infra", "strategy_matches": ["hot_theme", "momentum"]},
                           {"NVDA": "ai_semiconductor"})
    assert "AI_SEMICONDUCTOR" in tags     # from universe_meta
    assert "AI_INFRA" in tags             # from dsa primary_theme (normalized)
    assert "HOT_THEME" in tags and "MOMENTUM" in tags
    # de-duplicated
    assert len(tags) == len(set(tags))


def _seed_candidate(agent_root: Path, run_date: str, symbol: str) -> None:
    write_json(build_runtime_paths(agent_root, run_date=run_date).candidate_scores_path,
               {"symbols": {symbol: {"score": 70, "total_score": 70, "score_status": "scored", "components": {}}}})


def _seed_dsa(agent_root: Path, run_date: str, symbol: str, theme: str) -> None:
    write_json(build_runtime_paths(agent_root, run_date=run_date).dsa_signals_path,
               {"symbol_signals": {symbol: {"primary_theme": theme, "strategy_matches": ["momentum"]}}})


def _loader(series):
    def loader(symbol, start, end):
        return series.get(symbol, [])
    return loader


def test_thesis_attribution_aggregates_win_rate(tmp_path):
    (tmp_path / "src" / "config").mkdir(parents=True, exist_ok=True)
    write_json(tmp_path / "src" / "config" / "universe_meta.json", {"NVDA": {"theme": "ai_semiconductor"}})
    # two winning NVDA candidates on two dates
    series = {"SPY": [("2026-06-15", 400.0), ("2026-06-16", 401.0), ("2026-06-17", 402.0)],
              "NVDA": [("2026-06-15", 100.0), ("2026-06-16", 110.0), ("2026-06-17", 121.0)]}
    for rd in ("2026-06-15", "2026-06-16"):
        _seed_candidate(tmp_path, rd, "NVDA")
        _seed_dsa(tmp_path, rd, "NVDA", "AI Infra")

    report = thesis_attribution(tmp_path, horizons=(1,), price_loader=_loader(series), min_count=1)
    theses = {r["thesis"]: r for r in report["theses"]}
    assert "AI_SEMICONDUCTOR" in theses and "AI_INFRA" in theses and "MOMENTUM" in theses
    assert theses["AI_INFRA"]["win_rate"] == 1.0  # both up
    assert theses["AI_INFRA"]["count"] == 2


def test_thesis_min_count_filters_small_samples(tmp_path):
    (tmp_path / "src" / "config").mkdir(parents=True, exist_ok=True)
    write_json(tmp_path / "src" / "config" / "universe_meta.json", {"NVDA": {"theme": "ai_semiconductor"}})
    series = {"SPY": [("2026-06-15", 400.0), ("2026-06-16", 401.0)],
              "NVDA": [("2026-06-15", 100.0), ("2026-06-16", 110.0)]}
    _seed_candidate(tmp_path, "2026-06-15", "NVDA")
    report = thesis_attribution(tmp_path, horizons=(1,), price_loader=_loader(series), min_count=3)
    assert report["theses"] == []  # only 1 sample, below min_count


def test_markdown_renders(tmp_path):
    md = format_thesis_markdown({"generated_at": "x", "primary_horizon": 1, "sample_size": 0,
                                 "min_count": 3, "theses": []})
    assert "Thesis Attribution" in md
