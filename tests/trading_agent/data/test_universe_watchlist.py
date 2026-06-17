from __future__ import annotations

from pathlib import Path

from trading_agent.data.universe import parse_active_watchlist


def _config_dir(agent_root: Path) -> Path:
    config_dir = agent_root / "src" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def _write(path: Path, *symbols: str) -> None:
    path.write_text("\n".join(symbols) + "\n", encoding="utf-8")


def test_defaults_to_active_watchlist_when_no_registry(tmp_path):
    config_dir = _config_dir(tmp_path)
    _write(config_dir / "active_watchlist.txt", "NVDA", "MU")
    assert parse_active_watchlist(config_dir) == ["NVDA", "MU"]


def test_resolves_watchlist_filename_from_active_strategy(tmp_path):
    config_dir = _config_dir(tmp_path)
    _write(config_dir / "active_watchlist.txt", "NVDA")
    _write(config_dir / "watchlist_semis.txt", "SMH", "AMD")
    (config_dir / "strategy_registry.yaml").write_text(
        "active_strategy: semis_v2\n"
        "strategies:\n"
        "  semis_v2:\n"
        "    status: active\n"
        "    watchlist: watchlist_semis.txt\n",
        encoding="utf-8",
    )
    # Switching active_strategy to one with a different watchlist actually changes the symbols.
    assert parse_active_watchlist(config_dir) == ["SMH", "AMD"]


def test_explicit_override_filename_wins(tmp_path):
    config_dir = _config_dir(tmp_path)
    _write(config_dir / "active_watchlist.txt", "NVDA")
    _write(config_dir / "challenger_wl.txt", "PLTR")
    assert parse_active_watchlist(config_dir, watchlist_filename="challenger_wl.txt") == ["PLTR"]


def test_falls_back_to_universe_when_resolved_file_absent(tmp_path):
    config_dir = _config_dir(tmp_path)
    _write(config_dir / "universe.txt", "AAA", "BBB")
    (config_dir / "strategy_registry.yaml").write_text(
        "active_strategy: missing_wl\n"
        "strategies:\n"
        "  missing_wl:\n"
        "    watchlist: does_not_exist.txt\n",
        encoding="utf-8",
    )
    assert parse_active_watchlist(config_dir) == ["AAA", "BBB"]


def test_default_watchlist_field_is_backward_compatible(tmp_path):
    config_dir = _config_dir(tmp_path)
    _write(config_dir / "active_watchlist.txt", "NVDA", "TSM")
    (config_dir / "strategy_registry.yaml").write_text(
        "active_strategy: baseline_v1\n"
        "strategies:\n"
        "  baseline_v1:\n"
        "    watchlist: active_watchlist.txt\n",
        encoding="utf-8",
    )
    assert parse_active_watchlist(config_dir) == ["NVDA", "TSM"]
