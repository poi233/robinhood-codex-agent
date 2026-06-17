from __future__ import annotations

import json
from pathlib import Path

from trading_agent.core.context import build_runtime_paths
from trading_agent.features.factor_store import build_and_write_factor_layer


def _seed_config(agent_root: Path) -> None:
    cfg = agent_root / "src" / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "factor_profiles.json").write_text(
        (Path.cwd() / "src" / "config" / "factor_profiles.json").read_text(encoding="utf-8"), encoding="utf-8")


def _seed_daily(market_feed_dir: Path, symbol: str, n: int, base: float) -> None:
    path = market_feed_dir / "ohlcv" / symbol / "daily.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    bars = [{"close": base + i, "high": base + i + 1, "low": base + i - 1, "volume": 1_000_000} for i in range(n)]
    path.write_text(json.dumps(bars), encoding="utf-8")


def test_build_and_write_factor_layer_writes_panel_and_alpha(tmp_path):
    _seed_config(tmp_path)
    paths = build_runtime_paths(tmp_path, run_date="2026-06-15")
    _seed_daily(paths.market_feed_dir, "NVDA", 300, 100.0)
    _seed_daily(paths.market_feed_dir, "MU", 300, 50.0)
    _seed_daily(paths.market_feed_dir, "SPY", 300, 400.0)

    panel_path, alpha_path = build_and_write_factor_layer(tmp_path, "2026-06-15", active_symbols=["NVDA", "MU"])

    panel = json.loads(panel_path.read_text(encoding="utf-8"))
    alpha = json.loads(alpha_path.read_text(encoding="utf-8"))
    assert set(panel["symbols"]) == {"NVDA", "MU"}
    assert "momentum_12_1" in panel["symbols"]["NVDA"]
    assert panel["benchmark"] == "SPY"
    assert alpha["profile"] == "baseline_price_factors_v1"
    assert alpha["symbols"]["NVDA"]["factor_alpha_score"] is not None
    # path isolation: written under signals/ and planner/, not anywhere champion writes
    assert "signals/factor_panel.json" in str(panel_path)
    assert "planner/factor_alpha.json" in str(alpha_path)


def test_missing_symbol_ohlcv_reduces_coverage_not_crash(tmp_path):
    _seed_config(tmp_path)
    paths = build_runtime_paths(tmp_path, run_date="2026-06-15")
    _seed_daily(paths.market_feed_dir, "NVDA", 300, 100.0)
    # no SPY benchmark, no MU bars
    panel_path, alpha_path = build_and_write_factor_layer(tmp_path, "2026-06-15", active_symbols=["NVDA", "MU"])
    panel = json.loads(panel_path.read_text(encoding="utf-8"))
    assert "NVDA" in panel["symbols"]      # MU has no bars -> dropped, no crash
    assert "MU" not in panel["symbols"]
    # residual_momentum/beta need the benchmark -> None, but other factors present
    assert panel["symbols"]["NVDA"]["residual_momentum_6m"] is None
