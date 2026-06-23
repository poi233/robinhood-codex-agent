from __future__ import annotations

import json

from trading_agent.screener.config import load_screener_config
from trading_agent.screener.paths import screener_run_dir
from trading_agent.screener.pipeline import _resolve_will_apply, run_screen


def test_config_defaults_are_user_locked():
    cfg = load_screener_config(env={})
    assert cfg.enabled is True
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
    assert _resolve_will_apply(enabled=True, dry_run=True, apply=True) is False  # dry-run wins
    assert _resolve_will_apply(enabled=False, dry_run=False, apply=True) is True  # --apply forces
    assert _resolve_will_apply(enabled=True, dry_run=False, apply=None) is True  # follow flag
    assert _resolve_will_apply(enabled=False, dry_run=False, apply=None) is False


def test_pipeline_offline_no_universe_makes_no_change(tmp_path, monkeypatch):
    """No universe.txt + no codex → empty discovery, empty plan, no writes (fail-closed)."""
    monkeypatch.setenv("RUN_DATE_PT", "2026-06-21")
    monkeypatch.delenv("ENABLE_WEEKLY_SCREENER", raising=False)

    rc = run_screen(tmp_path)
    assert rc == 0

    status = json.loads((screener_run_dir(tmp_path) / "status.json").read_text(encoding="utf-8"))
    assert status["stage"] == "complete"
    assert status["applied"] is False
    assert status["added"] == []
    assert status["discovered_count"] == 0
    # audit is always written
    assert (screener_run_dir(tmp_path) / "universe_change.md").exists()


def test_pipeline_apply_mode_offline_still_writes_no_universe(tmp_path, monkeypatch):
    """Even with --apply, an empty plan (nothing discovered) must not create universe files."""
    monkeypatch.setenv("RUN_DATE_PT", "2026-06-21")
    monkeypatch.setenv("ENABLE_WEEKLY_SCREENER", "1")

    run_screen(tmp_path, apply=True)

    assert not (tmp_path / "src" / "config" / "universe.txt").exists()
    assert not (tmp_path / "src" / "config" / "universe_meta.json").exists()
    status = json.loads((screener_run_dir(tmp_path) / "status.json").read_text(encoding="utf-8"))
    assert status["will_apply"] is True
    assert status["applied"] is False  # nothing to apply
