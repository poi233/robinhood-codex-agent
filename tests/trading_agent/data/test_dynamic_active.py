from __future__ import annotations

import json
from pathlib import Path

from trading_agent.data.universe import load_dynamic_active, select_dynamic_active


def test_pins_always_included_and_topn_by_score():
    universe = ["SPY", "NVDA", "AMD", "MU", "LEU", "ASTS"]
    meta = {
        "NVDA": {"tier": "active", "screen_score": 9.0},
        "AMD": {"tier": "watch", "screen_score": 7.0},
        "MU": {"tier": "watch", "screen_score": 3.0},
        "LEU": {"tier": "watch", "screen_score": 8.0},
        "ASTS": {"tier": "watch"},  # unscored
    }
    sel = select_dynamic_active(universe=universe, meta=meta, pins=["SPY"], active_max=4)
    # SPY pinned, then top by score: NVDA(9), LEU(8), AMD(7) → total 4
    assert sel["active"] == ["SPY", "NVDA", "LEU", "AMD"]
    assert sel["pins"] == ["SPY"]


def test_passive_excluded_and_unscored_sorts_last():
    universe = ["A", "B", "C", "D"]
    meta = {
        "A": {"tier": "watch", "screen_score": 1.0},
        "B": {"tier": "passive", "screen_score": 99.0},  # excluded despite high score
        "C": {"tier": "watch"},  # unscored
        "D": {"tier": "watch", "screen_score": 2.0},
    }
    sel = select_dynamic_active(universe=universe, meta=meta, pins=[], active_max=10)
    assert "B" not in sel["active"]
    # scored first (D2 > A1), then unscored C last
    assert sel["active"] == ["D", "A", "C"]


def test_pins_exceeding_active_max_are_all_kept():
    universe = ["SPY", "QQQ", "NVDA", "AMD"]
    meta = {"NVDA": {"screen_score": 9.0}}
    sel = select_dynamic_active(universe=universe, meta=meta, pins=["SPY", "QQQ", "NVDA"], active_max=2)
    # all 3 pins kept even though active_max=2; no extra fill
    assert sel["active"] == ["SPY", "QQQ", "NVDA"]


def test_pins_deduped_and_uppercased():
    sel = select_dynamic_active(universe=["AMD"], meta={}, pins=["spy", "SPY", " qqq "], active_max=10)
    assert sel["pins"] == ["SPY", "QQQ"]


def _seed(config_dir: Path, universe: list[str], meta: dict, pins: list[str]) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "universe.txt").write_text("\n".join(universe) + "\n", encoding="utf-8")
    (config_dir / "universe_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    (config_dir / "active_watchlist.txt").write_text("\n".join(pins) + "\n", encoding="utf-8")


def test_load_dynamic_active_reads_files(tmp_path):
    config_dir = tmp_path / "src" / "config"
    _seed(
        config_dir,
        universe=["SPY", "NVDA", "AMD"],
        meta={"NVDA": {"screen_score": 9.0}, "AMD": {"screen_score": 2.0}},
        pins=["SPY"],
    )
    sel = load_dynamic_active(config_dir, active_max=2)
    assert sel["active"] == ["SPY", "NVDA"]  # SPY pin + top score NVDA, capped at 2


def test_load_dynamic_active_missing_meta_is_pins_plus_universe_order(tmp_path):
    config_dir = tmp_path / "src" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "universe.txt").write_text("SPY\nNVDA\nAMD\n", encoding="utf-8")
    (config_dir / "active_watchlist.txt").write_text("SPY\n", encoding="utf-8")
    # no universe_meta.json → all unscored, universe order
    sel = load_dynamic_active(config_dir, active_max=3)
    assert sel["active"] == ["SPY", "NVDA", "AMD"]
