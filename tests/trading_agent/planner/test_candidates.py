from __future__ import annotations

from pathlib import Path

from trading_agent.core.io import write_json
from trading_agent.planner.candidates import build_candidate_snapshot


def _make_universe(config_dir: Path, symbols: list[str]) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "universe.txt").write_text("\n".join(symbols) + "\n", encoding="utf-8")


def test_selected_symbols_default_cap_is_20(tmp_path: Path) -> None:
    agent_root = tmp_path
    config_dir = agent_root / "src" / "config"
    symbols = [f"SYM{i}" for i in range(30)]
    _make_universe(config_dir, symbols)
    write_json(
        agent_root / "runtime" / "state" / "runs" / "2026-06-15" / "signals" / "dsa_signals.json",
        {"selected_candidates": symbols},
    )

    snapshot = build_candidate_snapshot(agent_root, "2026-06-15")

    assert len(snapshot["selected_symbols"]) == 20


def test_selected_symbols_cap_is_configurable(tmp_path: Path) -> None:
    agent_root = tmp_path
    config_dir = agent_root / "src" / "config"
    symbols = [f"SYM{i}" for i in range(30)]
    _make_universe(config_dir, symbols)
    (config_dir / "scoring_profiles.yaml").write_text(
        "default_profile: aggressive_growth\n"
        "max_scored_candidates: 5\n"
        "profiles:\n"
        "  aggressive_growth:\n"
        "    watchlist_threshold: 35\n"
        "    trade_threshold: 50\n"
        "    high_conviction_threshold: 80\n"
        "    min_effective_coverage: 0.5\n",
        encoding="utf-8",
    )
    write_json(
        agent_root / "runtime" / "state" / "runs" / "2026-06-15" / "signals" / "dsa_signals.json",
        {"selected_candidates": symbols},
    )

    snapshot = build_candidate_snapshot(agent_root, "2026-06-15")

    assert len(snapshot["selected_symbols"]) == 5
