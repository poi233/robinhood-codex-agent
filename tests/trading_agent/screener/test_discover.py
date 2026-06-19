from __future__ import annotations

import json
from pathlib import Path

from trading_agent.screener.discover import parse_discovered, run_discovery
from trading_agent.screener.paths import screener_run_dir


def _seed_universe(root: Path, symbols: list[str]) -> None:
    config_dir = root / "src" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "universe.txt").write_text("\n".join(symbols) + "\n", encoding="utf-8")


def test_parse_discovered_handles_shapes_and_excludes_existing(tmp_path):
    path = tmp_path / "discovered.json"
    path.write_text(
        json.dumps(
            {
                "candidates": [
                    {"symbol": "sive", "theme": "photonics", "thesis": "laser chokepoint"},
                    {"ticker": "FOCI"},
                    "NVDA",  # already in universe → dropped
                    {"symbol": "FOCI"},  # duplicate → dropped
                    {"symbol": ""},  # blank → dropped
                    42,  # junk → dropped
                ]
            }
        ),
        encoding="utf-8",
    )
    out = parse_discovered(path, existing={"NVDA"})
    symbols = [r["symbol"] for r in out]
    assert symbols == ["SIVE", "FOCI"]
    assert out[0]["theme"] == "photonics"


def test_parse_discovered_missing_or_malformed_is_empty(tmp_path):
    assert parse_discovered(tmp_path / "nope.json", existing=set()) == []
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert parse_discovered(bad, existing=set()) == []


def test_run_discovery_injects_overrides_and_reads_result(tmp_path, monkeypatch):
    monkeypatch.setenv("RUN_DATE_PT", "2026-06-21")
    _seed_universe(tmp_path, ["NVDA", "AVGO"])

    captured = {}

    def fake_runner(run_kind, agent_root, prompt_file, *, runtime_overrides=None):
        captured["run_kind"] = run_kind
        captured["overrides"] = runtime_overrides
        # emulate Codex writing the discovery file
        out_path = Path(runtime_overrides["DISCOVERED_PATH"])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps({"candidates": [{"symbol": "SIVE"}, {"symbol": "AVGO"}]}),  # AVGO already in universe
            encoding="utf-8",
        )
        return 0

    result = run_discovery(tmp_path, prompt_runner=fake_runner, limit=10)

    assert captured["run_kind"] == "screener_discover"
    assert captured["overrides"]["EXISTING_UNIVERSE_SYMBOLS"] == "NVDA,AVGO"
    assert captured["overrides"]["SCREEN_DISCOVER_LIMIT"] == "10"
    assert result["discovered_symbols"] == ["SIVE"]  # AVGO excluded as existing
    assert result["status"] == 0
    assert Path(result["discovered_path"]) == screener_run_dir(tmp_path) / "discovered.json"


def test_run_discovery_fail_closed_when_no_file_written(tmp_path, monkeypatch):
    monkeypatch.setenv("RUN_DATE_PT", "2026-06-21")
    _seed_universe(tmp_path, ["NVDA"])

    def silent_runner(run_kind, agent_root, prompt_file, *, runtime_overrides=None):
        return 0  # writes nothing (e.g. dry-run / offline)

    result = run_discovery(tmp_path, prompt_runner=silent_runner)
    assert result["discovered"] == []
    assert result["discovered_symbols"] == []


def test_run_discovery_survives_missing_codex_binary(tmp_path, monkeypatch):
    monkeypatch.setenv("RUN_DATE_PT", "2026-06-21")
    _seed_universe(tmp_path, ["NVDA"])

    def raising_runner(run_kind, agent_root, prompt_file, *, runtime_overrides=None):
        raise FileNotFoundError("missing codex executable")

    result = run_discovery(tmp_path, prompt_runner=raising_runner)
    assert result["status"] == 127
    assert result["discovered"] == []
