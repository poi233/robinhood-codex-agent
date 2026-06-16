from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_agent.core.context import build_experiment_paths, build_runtime_paths
from trading_agent.planner.risk_overlay import build_risk_overlay
from trading_agent.planner.scoring_profiles import load_scoring_profile
from trading_agent.policy.engine import generate_order_intent
from trading_agent.policy.models import PolicyInputs


def _read_json_or_empty(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _challenger_scoring_profile(agent_root: Path, experiment: dict[str, Any]) -> dict[str, Any]:
    """Champion scoring profile with the experiment's scoring mutation applied.

    Uses G-pre's profile-by-name resolution; falls back to the env/default profile.
    Only scoring-module numeric overrides are applied here (the lever G3 currently moves).
    """
    config_dir = build_runtime_paths(agent_root).config_dir
    base = dict(load_scoring_profile(config_dir, profile_name=experiment.get("scoring_profile") or None))
    if experiment.get("module") == "scoring" and experiment.get("field") and experiment.get("proposed") is not None:
        base[str(experiment["field"])] = float(experiment["proposed"])
    return base


def build_challenger_risk_overlay(
    agent_root: Path,
    run_date: str,
    experiment: dict[str, Any],
    *,
    trading_mode: str,
    risk_tier: int,
) -> dict[str, Any]:
    """Re-run the pure risk overlay with the challenger's scoring profile, reusing the
    champion's already-persisted premarket artifacts. Never writes the champion overlay.
    """
    paths = build_runtime_paths(agent_root, run_date=run_date)
    risk_config = _read_json_or_empty(paths.config_dir / "risk_tiers.json")
    risk_caps = risk_config.get(str(risk_tier)) or {}
    return build_risk_overlay(
        run_date=run_date,
        trading_mode=trading_mode,
        risk_tier=risk_tier,
        risk_caps=risk_caps,
        market_calendar=_read_json_or_empty(paths.market_calendar_path),
        capital_snapshot=_read_json_or_empty(paths.capital_snapshot_path),
        account_snapshot=_read_json_or_empty(paths.account_snapshot_path),
        candidate_scores=_read_json_or_empty(paths.candidate_scores_path),
        data_status_summary=_read_json_or_empty(paths.data_status_summary_path),
        scoring_profile=_challenger_scoring_profile(agent_root, experiment),
    )


def build_challenger_inputs(champion_inputs: PolicyInputs, challenger_overlay: dict[str, Any]) -> PolicyInputs:
    """A copy of the champion inputs with the challenger's overlay swapped in.

    The intraday policy reads tradability from risk_overlay.symbol_trade_rules and the
    plan gates (market_regime/allowed_actions/today_watchlist) from daily_plan, so both
    are re-derived from the challenger overlay. All other inputs (quotes, positions,
    watch levels, profile) are shared with the champion run unchanged.
    """
    champion_plan = champion_inputs.daily_plan or {}
    challenger_plan = {
        **champion_plan,
        "market_regime": challenger_overlay.get("market_regime", champion_plan.get("market_regime")),
        "allowed_actions": challenger_overlay.get("allowed_actions", champion_plan.get("allowed_actions")),
        "today_watchlist": challenger_overlay.get("today_watchlist", champion_plan.get("today_watchlist")),
        "symbol_trade_rules": challenger_overlay.get("symbol_trade_rules", champion_plan.get("symbol_trade_rules")),
    }
    return replace(champion_inputs, risk_overlay=challenger_overlay, daily_plan=challenger_plan)


def run_shadow_experiment(
    agent_root: Path,
    *,
    run_date: str,
    experiment: dict[str, Any],
    champion_inputs: PolicyInputs,
    trading_mode: str,
    risk_tier: int,
) -> dict[str, Any]:
    """Run one challenger over the champion's inputs and append its decision to the
    challenger's isolated shadow_decisions.jsonl. Returns a compact decision summary.
    Champion ledgers are never touched.
    """
    overlay = build_challenger_risk_overlay(agent_root, run_date, experiment, trading_mode=trading_mode, risk_tier=risk_tier)
    challenger_inputs = build_challenger_inputs(champion_inputs, overlay)
    decision = generate_order_intent(challenger_inputs)

    strategy_id = str(experiment.get("challenger_strategy_id") or experiment.get("experiment_id") or "challenger")
    exp_paths = build_experiment_paths(agent_root, run_date=run_date, strategy_id=strategy_id)
    exp_paths.shadow_decisions_log_path.parent.mkdir(parents=True, exist_ok=True)
    intent = decision.intent
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_date": run_date,
        "experiment_id": experiment.get("experiment_id"),
        "challenger_strategy_id": strategy_id,
        "decision": decision.decision,
        "symbol": intent.symbol if intent else None,
        "side": intent.side if intent else None,
        "blocked_reasons": list(decision.blocked_reasons),
    }
    with exp_paths.shadow_decisions_log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
    return record


def run_active_shadow_experiments(
    agent_root: Path,
    *,
    run_date: str,
    champion_inputs: PolicyInputs,
    trading_mode: str,
    risk_tier: int,
) -> list[dict[str, Any]]:
    """Run every `active_shadow` experiment over the champion's inputs. Each challenger is
    isolated; one failing challenger never blocks the others (or the champion intraday run).
    """
    from trading_agent.growth.experiment_queue import list_experiments

    results: list[dict[str, Any]] = []
    for experiment in list_experiments(agent_root, status="active_shadow"):
        try:
            results.append(
                run_shadow_experiment(
                    agent_root,
                    run_date=run_date,
                    experiment=experiment,
                    champion_inputs=champion_inputs,
                    trading_mode=trading_mode,
                    risk_tier=risk_tier,
                )
            )
        except Exception as exc:  # noqa: BLE001 - shadow is best-effort, must never break champion
            results.append({"experiment_id": experiment.get("experiment_id"), "error": str(exc)})
    return results
