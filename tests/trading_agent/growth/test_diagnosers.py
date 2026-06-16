import json
from pathlib import Path

from trading_agent.growth.diagnosers import DIAGNOSERS, run_all
from trading_agent.growth.observations import GrowthContext


def test_registry_exposes_named_diagnosers():
    assert "scoring" in DIAGNOSERS
    assert "setups" in DIAGNOSERS


def test_setups_diagnoser_flags_dominant_setup_gates():
    ctx = GrowthContext(
        agent_root=Path("/nonexistent"),
        run_dates=["2026-06-15"],
        replay={"blocked_reasons": {"reason_counts": {"outside_entry_zone": 6, "missing_quote": 1}}},
    )
    result = run_all(ctx)
    setup_obs = result["setups"]
    assert any(o["type"] == "setup_gates_dominate_no_trades" for o in setup_obs)


def test_scoring_diagnoser_flags_recurring_theme_concentration(tmp_path):
    run_dir = tmp_path / "runtime" / "state" / "runs" / "2026-06-15" / "planner"
    run_dir.mkdir(parents=True)
    (run_dir / "premarket_diagnostics.json").write_text(
        json.dumps({"warnings": ["theme_concentration_exceeded:tradable:ai_semiconductor:70%>50%"]}),
        encoding="utf-8",
    )
    ctx = GrowthContext(agent_root=tmp_path, run_dates=["2026-06-15"], replay={})
    result = run_all(ctx)
    assert any(o["type"] == "recurring_theme_concentration" for o in result["scoring"])
