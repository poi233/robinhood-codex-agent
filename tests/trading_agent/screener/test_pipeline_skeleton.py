from __future__ import annotations

import json

from trading_agent.screener.config import load_screener_config
from trading_agent.screener.paths import screener_run_dir
from trading_agent.screener.pipeline import _resolve_will_apply, run_screen


def test_config_defaults_are_user_locked():
    cfg = load_screener_config(env={})
    assert cfg.enabled is False
    assert cfg.max_adds_per_week == 5
    assert cfg.universe_max == 120
    assert cfg.min_dollar_volume == 20_000_000.0
    assert cfg.require_uptrend is True


def test_config_reads_env_overrides():
    cfg = load_screener_config(
        env={
            "ENABLE_WEEKLY_SCREENER": "1",
            "SCREEN_MAX_ADDS_PER_WEEK": "3",
            "UNIVERSE_MAX": "80",
            "SCREEN_MIN_DOLLAR_VOL": "5000000",
            "SCREEN_REQUIRE_UPTREND": "0",
        }
    )
    assert cfg.enabled is True
    assert cfg.max_adds_per_week == 3
    assert cfg.universe_max == 80
    assert cfg.min_dollar_volume == 5_000_000.0
    assert cfg.require_uptrend is False


def test_config_bad_ints_fall_back_to_defaults():
    cfg = load_screener_config(env={"SCREEN_MAX_ADDS_PER_WEEK": "oops", "UNIVERSE_MAX": ""})
    assert cfg.max_adds_per_week == 5
    assert cfg.universe_max == 120


def test_resolve_will_apply_precedence():
    # dry-run always wins
    assert _resolve_will_apply(enabled=True, dry_run=True, apply=True) is False
    # explicit --apply forces writing even when flag is off
    assert _resolve_will_apply(enabled=False, dry_run=False, apply=True) is True
    # no overrides → follow the flag
    assert _resolve_will_apply(enabled=True, dry_run=False, apply=None) is True
    assert _resolve_will_apply(enabled=False, dry_run=False, apply=None) is False


def test_skeleton_writes_status_report_only_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("RUN_DATE_PT", "2026-06-21")
    monkeypatch.delenv("ENABLE_WEEKLY_SCREENER", raising=False)

    rc = run_screen(tmp_path)
    assert rc == 0

    status_path = screener_run_dir(tmp_path) / "status.json"
    assert status_path.exists()
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["stage"] == "skeleton"
    assert status["enabled_flag"] is False
    assert status["will_apply"] is False
    assert status["config"]["universe_max"] == 120


def test_skeleton_never_creates_or_touches_universe_files(tmp_path, monkeypatch):
    monkeypatch.setenv("RUN_DATE_PT", "2026-06-21")
    monkeypatch.setenv("ENABLE_WEEKLY_SCREENER", "1")

    run_screen(tmp_path, apply=True)

    # The skeleton must not write any universe config, even in apply mode.
    assert not (tmp_path / "src" / "config" / "universe.txt").exists()
    assert not (tmp_path / "src" / "config" / "universe_meta.json").exists()
    status = json.loads((screener_run_dir(tmp_path) / "status.json").read_text(encoding="utf-8"))
    assert status["will_apply"] is True
