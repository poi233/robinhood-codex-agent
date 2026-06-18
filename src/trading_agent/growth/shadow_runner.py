from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_agent.core.context import build_experiment_paths, build_experiment_runtime_paths, build_runtime_paths
from trading_agent.planner.risk_overlay import build_risk_overlay
from trading_agent.planner.scoring_profiles import load_scoring_profile
from trading_agent.policy.engine import generate_order_intent
from trading_agent.policy.models import PolicyInputs


def _challenger_starting_cash() -> float:
    try:
        return float(os.environ.get("PAPER_STARTING_CASH", "400000"))
    except ValueError:
        return 400000.0


def _simulate_challenger_paper(agent_root: Path, run_date: str, strategy_id: str,
                               champion_inputs: PolicyInputs, challenger_inputs: PolicyInputs) -> None:
    """Seed/reconcile the challenger's isolated paper ledger and overlay its own account/positions/
    pending into challenger_inputs, so the challenger decides and trades from ITS OWN state."""
    from trading_agent.paper.broker import reconcile_pending_paper_orders, record_paper_day_start
    from trading_agent.policy.loaders import hydrate_paper_ledger

    exp_runtime = build_experiment_runtime_paths(agent_root, run_date=run_date, strategy_id=strategy_id)
    starting_cash = _challenger_starting_cash()
    record_paper_day_start(agent_root, run_date=run_date, starting_cash=starting_cash, paths_override=exp_runtime)
    reconcile_pending_paper_orders(agent_root, run_date=run_date, quotes=champion_inputs.quotes,
                                   starting_cash=starting_cash, paths_override=exp_runtime)
    hydrate_paper_ledger(challenger_inputs, exp_runtime)


def _apply_challenger_fill(agent_root: Path, run_date: str, strategy_id: str, decision) -> None:
    from trading_agent.paper.broker import apply_paper_intent

    exp_runtime = build_experiment_runtime_paths(agent_root, run_date=run_date, strategy_id=strategy_id)
    apply_paper_intent(agent_root, run_date=run_date, decision=decision,
                       starting_cash=_challenger_starting_cash(), paths_override=exp_runtime)


def _read_json_or_empty(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _shadow_rescore_enabled() -> bool:
    """H4: when on, a challenger may carry a multi-change `changes` list (re-weight several scoring
    components at once), not just the single scoring threshold G3 moves. Default off keeps the shadow
    runner's behavior byte-for-byte. The whole shadow path is already double-isolated (writes only
    experiments/<id>/, never the champion), so this only widens what a challenger can express."""
    return str(os.environ.get("ENABLE_SHADOW_RESCORE", "0") or "0") == "1"


def _challenger_scoring_profile(agent_root: Path, experiment: dict[str, Any]) -> dict[str, Any]:
    """Champion scoring profile with the experiment's scoring mutation(s) applied.

    Uses G-pre's profile-by-name resolution; falls back to the env/default profile. The single
    `field`/`proposed` mutation (the lever G3 moves) is always applied. With ENABLE_SHADOW_RESCORE,
    a `changes` list of additional scoring-module overrides is also applied — so a challenger can
    re-weight several components at once (e.g. validate an E2 weight suggestion in shadow).
    """
    config_dir = build_runtime_paths(agent_root).config_dir
    base = dict(load_scoring_profile(config_dir, profile_name=experiment.get("scoring_profile") or None))
    if experiment.get("module") == "scoring" and experiment.get("field") and experiment.get("proposed") is not None:
        base[str(experiment["field"])] = float(experiment["proposed"])
    if _shadow_rescore_enabled():
        for change in experiment.get("changes") or []:
            if not isinstance(change, dict):
                continue
            if change.get("module") == "scoring" and change.get("field") and change.get("proposed") is not None:
                try:
                    base[str(change["field"])] = float(change["proposed"])
                except (TypeError, ValueError):
                    continue
    return base


def _challenger_rescore_config(experiment: dict[str, Any]) -> dict[str, Any] | None:
    """H4 expensive path: extract analyzer/factor re-scoring levers from the experiment's changes.

    Only active under ENABLE_SHADOW_RESCORE. Recognizes:
      - {module: "analyzer", field: "<name>.enabled", proposed: false} → disable component <name>
      - {module: "scoring", field: "<name>_weight", proposed: <float>} → override component weight
      - {module: "factor", field: "factor_alpha_weight", proposed: <float>} → fold factor_alpha in
    Returns None when the challenger needs no re-scoring (pure threshold/weight-profile challenger),
    so the cheap path (champion candidate_scores reuse) is kept byte-for-byte.
    """
    if not _shadow_rescore_enabled():
        return None
    disabled: set[str] = set()
    component_weights: dict[str, float] = {}
    factor_alpha_weight = 0.0
    for change in experiment.get("changes") or []:
        if not isinstance(change, dict):
            continue
        module = str(change.get("module") or "")
        field = str(change.get("field") or "")
        proposed = change.get("proposed")
        if module == "analyzer" and field.endswith(".enabled"):
            name = field[: -len(".enabled")]
            if proposed in (False, 0, "false", "0"):
                disabled.add(name)
        elif module == "scoring" and field.endswith("_weight"):
            try:
                component_weights[field[: -len("_weight")]] = float(proposed)
            except (TypeError, ValueError):
                continue
        elif module == "factor" and field == "factor_alpha_weight":
            try:
                factor_alpha_weight = float(proposed)
            except (TypeError, ValueError):
                continue
    if not disabled and not component_weights and factor_alpha_weight <= 0:
        return None
    return {
        "disabled_components": disabled,
        "component_weights": component_weights,
        "factor_alpha_weight": factor_alpha_weight,
    }


def _challenger_candidate_scores(agent_root: Path, run_date: str, experiment: dict[str, Any]) -> dict[str, Any]:
    """The candidate_scores the challenger overlay should consume.

    Cheap path (default / threshold challenger): the champion's persisted candidate_scores.
    Expensive path (H4, ENABLE_SHADOW_RESCORE + analyzer/factor changes): re-aggregate every
    candidate under the challenger config, folding in the persisted factor_alpha layer if asked.
    """
    paths = build_runtime_paths(agent_root, run_date=run_date)
    champion_scores = _read_json_or_empty(paths.candidate_scores_path)
    config = _challenger_rescore_config(experiment)
    if config is None:
        return champion_scores
    from trading_agent.planner.scoring import rescore_candidate_scores

    factor_alpha = _read_json_or_empty(paths.factor_alpha_path) if config["factor_alpha_weight"] > 0 else None
    return rescore_candidate_scores(
        champion_scores,
        component_weights=config["component_weights"],
        disabled_components=config["disabled_components"],
        factor_alpha=factor_alpha,
        factor_alpha_weight=config["factor_alpha_weight"],
    )


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

    With ENABLE_SHADOW_RESCORE and analyzer/factor changes, the candidate scores themselves are
    re-aggregated under the challenger config (H4 expensive path) before the overlay runs.
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
        candidate_scores=_challenger_candidate_scores(agent_root, run_date, experiment),
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

    strategy_id = str(experiment.get("challenger_strategy_id") or experiment.get("experiment_id") or "challenger")

    # G9: give the challenger its own isolated paper ledger under experiments/<id>/paper/, so its
    # fill rate / drawdown / PnL are real and comparable — and the champion ledger is never touched.
    if trading_mode == "paper":
        _simulate_challenger_paper(agent_root, run_date, strategy_id, champion_inputs, challenger_inputs)

    decision = generate_order_intent(challenger_inputs)

    if trading_mode == "paper" and decision.decision == "would_trade":
        _apply_challenger_fill(agent_root, run_date, strategy_id, decision)

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
