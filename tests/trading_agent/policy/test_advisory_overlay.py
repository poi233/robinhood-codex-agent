import json
from pathlib import Path

from trading_agent.core.context import build_runtime_paths
from trading_agent.policy.advisory_overlay import (
    AdvisoryOverlay,
    SymbolOverlay,
    build_advisory_overlay,
    load_advisory_artifacts,
    overlay_for_symbol,
)
from trading_agent.policy.models import PolicyInputs


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_load_advisory_artifacts_reads_only_fresh_payloads(tmp_path: Path) -> None:
    paths = build_runtime_paths(tmp_path, run_date="2026-06-18")
    write_json(paths.factor_alpha_path, {"date": "2026-06-18", "symbols": {"NVDA": {"factor_alpha_score": 82}}})
    write_json(paths.ai_signals_path, {"asof_date": "2026-06-17", "layers": {"kronos": {}}})
    write_json(paths.planner_dir / "regime_state.json", {"date": "2026-06-18", "regime": "risk_off"})
    write_json(paths.planner_dir / "portfolio_target.json", {"date": "2026-06-18", "breaches": {}})

    artifacts = load_advisory_artifacts(paths)

    assert artifacts["factor_alpha"]["symbols"]["NVDA"]["factor_alpha_score"] == 82
    assert artifacts["ai_signals"] == {}
    assert artifacts["regime_state"]["regime"] == "risk_off"
    assert artifacts["portfolio_target"]["breaches"] == {}


def test_build_advisory_overlay_combines_rank_delta_with_risk_tightening() -> None:
    inputs = PolicyInputs(
        run_date="2026-06-18",
        trading_mode="paper",
        risk_tier=4,
        today_allowlist=["NVDA", "PLTR"],
    )
    artifacts = {
        "factor_alpha": {
            "symbols": {
                "NVDA": {
                    "factor_alpha_score": 88.0,
                    "factor_components": {"momentum_12_1": 91.0},
                    "risk_flags": [],
                }
            }
        },
        "ai_signals": {
            "layers": {
                "kronos": {
                    "symbols": {
                        "NVDA": {
                            "direction": "long",
                            "confidence": 0.82,
                            "reason_codes": ["kronos_uptrend"],
                        }
                    }
                }
            }
        },
        "regime_state": {"regime": "risk_off", "applied_multiplier": 0.5, "reasons": ["spy_below_ma"]},
        "portfolio_target": {
            "position_weights": {"NVDA": 0.09},
            "theme_by_symbol": {"NVDA": "ai_semiconductor"},
            "breaches": {"oversize_positions": ["NVDA"], "overexposed_themes": []},
        },
    }

    overlay = build_advisory_overlay(inputs, artifacts)
    nvda = overlay_for_symbol(overlay, "NVDA")
    pltr = overlay_for_symbol(overlay, "PLTR")

    assert isinstance(overlay, AdvisoryOverlay)
    assert isinstance(nvda, SymbolOverlay)
    assert nvda.block_buy is True
    assert nvda.rank_delta == 5.0
    assert nvda.size_multiplier == 0.0
    assert "regime_blocks_new_buy" in nvda.blocked_reasons
    assert "portfolio_oversize_position" in nvda.blocked_reasons
    assert nvda.components["factor_alpha"]["score"] == 88.0
    assert nvda.components["ai"]["kronos"]["direction"] == "long"
    assert nvda.components["regime"]["regime"] == "risk_off"
    assert nvda.components["portfolio"]["position_weight"] == 0.09
    assert pltr.components["regime"]["regime"] == "risk_off"
    assert pltr.components["factor_alpha"] == {}


def test_build_advisory_overlay_applies_regime_size_multiplier_without_increase() -> None:
    inputs = PolicyInputs(
        run_date="2026-06-18",
        trading_mode="paper",
        risk_tier=4,
        today_allowlist=["NVDA"],
    )
    artifacts = {
        "factor_alpha": {},
        "ai_signals": {},
        "regime_state": {"regime": "neutral", "applied_multiplier": 0.5},
        "portfolio_target": {},
    }

    overlay = build_advisory_overlay(inputs, artifacts)
    nvda = overlay_for_symbol(overlay, "NVDA")

    assert nvda.block_buy is False
    assert nvda.size_multiplier == 0.5
    assert nvda.components["regime"]["applied_multiplier"] == 0.5


def test_build_advisory_overlay_penalizes_weak_factor_and_negative_ai_without_blocking() -> None:
    inputs = PolicyInputs(
        run_date="2026-06-18",
        trading_mode="paper",
        risk_tier=4,
        today_allowlist=["AMD"],
    )
    artifacts = {
        "factor_alpha": {"symbols": {"AMD": {"factor_alpha_score": 22.0}}},
        "ai_signals": {
            "layers": {
                "dsa": {
                    "symbols": {
                        "AMD": {
                            "direction": "short",
                            "confidence": 0.75,
                            "warning_codes": ["avoid_chase"],
                        }
                    }
                }
            }
        },
        "regime_state": {},
        "portfolio_target": {},
    }

    overlay = build_advisory_overlay(inputs, artifacts)
    amd = overlay_for_symbol(overlay, "AMD")

    assert amd.rank_delta == -5.0
    assert amd.block_buy is False
    assert amd.size_multiplier == 1.0
    assert "factor_alpha_low" in amd.reason_codes
    assert "ai_dsa_bearish" in amd.reason_codes


def test_overlay_for_symbol_returns_empty_symbol_overlay_for_unknown_symbol() -> None:
    overlay = AdvisoryOverlay(run_date="2026-06-18")

    symbol_overlay = overlay_for_symbol(overlay, "MSFT")

    assert symbol_overlay.symbol == "MSFT"
    assert symbol_overlay.rank_delta == 0.0
    assert symbol_overlay.size_multiplier == 1.0
    assert symbol_overlay.block_buy is False
    assert symbol_overlay.blocked_reasons == []
    assert symbol_overlay.components == {}
