from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from trading_agent.core.config import load_env_files, load_runtime_config
from trading_agent.core.context import build_runtime_paths, resolve_agent_root
from trading_agent.core.time import PT
from trading_agent.core.time import pt_date_string
from trading_agent.data.live_quotes import fetch_yfinance_live_quotes
from trading_agent.notifications.email import send_trade_email_notification
from trading_agent.notifications.trade_email_reports import build_intraday_trade_email_body
from trading_agent.paper.broker import apply_paper_intent, reconcile_pending_paper_orders, record_paper_day_start
from trading_agent.policy.engine import generate_order_intent
from trading_agent.policy.loaders import load_policy_inputs
from trading_agent.policy.models import PolicyDecision
from trading_agent.prompts.codex import run_codex_prompt
from trading_agent.strategy.manifest import build_run_manifest


def _append_local_decision(agent_root: Path, decision: str, reason: str, *, run_date: str | None = None) -> None:
    log_path = build_runtime_paths(agent_root, run_date=run_date).decisions_log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": datetime.now(tz=PT).strftime("%Y-%m-%dT%H:%M:%S%z"),
        "run_kind": "intraday",
        "trading_mode": os.environ.get("TRADING_MODE", "paper"),
        "decision": decision,
        "action_taken": "none",
        "reason": reason,
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def _append_intraday_rankings(agent_root: Path, inputs, *, run_date: str | None = None) -> None:
    """Persist the intraday ranking scores (trade_readiness / price_setup / components).

    These are computed transiently during ranking and were never written before, so E1
    forward-return attribution and E2 weight calibration had no historical data for the
    intraday six-component scores. One JSONL row per ranked candidate per intraday run,
    using the same pure rank_candidates() the buy policy uses, so the persisted scores
    match the decision's view of the world. Read-only w.r.t. trading behavior.
    """
    from trading_agent.policy.candidate_selector import rank_candidates

    ranked, _blocked = rank_candidates(inputs)
    if not ranked:
        return
    log_path = build_runtime_paths(agent_root, run_date=run_date).intraday_rankings_log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(tz=PT).strftime("%Y-%m-%dT%H:%M:%S%z")
    with log_path.open("a", encoding="utf-8") as handle:
        for candidate in ranked:
            handle.write(
                json.dumps(
                    {
                        "timestamp": timestamp,
                        "run_date": run_date,
                        "symbol": candidate.symbol,
                        "trade_readiness_score": candidate.trade_readiness_score,
                        "price_setup_score": candidate.price_setup_score,
                        "candidate_score": candidate.candidate_score,
                        "technical_score": candidate.technical_score,
                        "research_score": candidate.research_score,
                        "catalyst_score": candidate.catalyst_score,
                        "liquidity_score": candidate.liquidity_score,
                    }
                )
                + "\n"
            )


def _append_policy_decision(agent_root: Path, decision: PolicyDecision, *, run_date: str | None = None) -> None:
    log_path = build_runtime_paths(agent_root, run_date=run_date).decisions_log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)
    payload = decision.to_json_dict(timestamp=datetime.now(tz=PT).strftime("%Y-%m-%dT%H:%M:%S%z"))
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def _is_weekday_pt() -> bool:
    return datetime.now(tz=PT).weekday() < 5


def _is_intraday_window_pt() -> bool:
    now = datetime.now(tz=PT)
    current = now.hour * 60 + now.minute
    return 6 * 60 + 45 <= current <= 12 * 60 + 55


def run_intraday_pipeline(*, dry_run: bool) -> int:
    del dry_run
    agent_root = resolve_agent_root()
    load_env_files(agent_root)
    run_date = pt_date_string()
    runtime = load_runtime_config(agent_root)
    if not _is_weekday_pt() and os.environ.get("ALLOW_WEEKEND_RUN", "0") != "1":
        _append_local_decision(agent_root, "calendar_skip", "not_a_weekday_pt", run_date=run_date)
        return 0
    if not _is_intraday_window_pt() and os.environ.get("ALLOW_OUTSIDE_MARKET_TEST", "0") != "1":
        _append_local_decision(agent_root, "time_window_skip", "outside_intraday_window_pt", run_date=run_date)
        return 0
    kill_switch_present = (agent_root / "KILL_SWITCH").exists()
    if kill_switch_present and runtime.trading_mode != "paper" and os.environ.get("ALLOW_KILL_SWITCH_PAPER_TEST", "0") != "1":
        _append_local_decision(agent_root, "kill_switch_skip", "KILL_SWITCH_present", run_date=run_date)
        return 0
    effective_risk_tier = runtime.effective_risk_tier
    build_run_manifest(agent_root, run_date)
    paper_starting_cash = float(os.environ.get("PAPER_STARTING_CASH", "400000"))
    inputs = load_policy_inputs(
        agent_root,
        run_date=run_date,
        trading_mode=runtime.trading_mode,
        risk_tier=effective_risk_tier,
        robinhood_gateway=None,
        quote_provider=fetch_yfinance_live_quotes,
        require_live_quotes=True,
    )
    if runtime.trading_mode == "paper":
        pending_fill_events = reconcile_pending_paper_orders(
            agent_root,
            run_date=run_date,
            quotes=inputs.quotes,
            starting_cash=paper_starting_cash,
        )
        if pending_fill_events:
            inputs = load_policy_inputs(
                agent_root,
                run_date=run_date,
                trading_mode=runtime.trading_mode,
                risk_tier=effective_risk_tier,
                robinhood_gateway=None,
                quote_provider=fetch_yfinance_live_quotes,
                require_live_quotes=True,
            )
    if runtime.trading_mode == "paper":
        record_paper_day_start(
            agent_root,
            run_date=run_date,
            starting_cash=paper_starting_cash,
            positions=inputs.positions,
        )
    decision = generate_order_intent(inputs)
    if runtime.trading_mode == "paper" and decision.decision == "would_trade":
        paper_result = apply_paper_intent(
            agent_root,
            run_date=run_date,
            decision=decision,
            starting_cash=paper_starting_cash,
        )
        if paper_result.applied:
            decision = replace(decision, action_taken="paper_fill")
            if decision.intent is not None:
                paths = build_runtime_paths(agent_root, run_date=run_date)
                send_trade_email_notification(
                    agent_root,
                    event_tag="TRADE_EXECUTED",
                    title=f"模拟盘{decision.intent.side.upper()}成交",
                    summary=(
                        f"模拟盘已按策略执行 {decision.intent.side.upper()} {decision.intent.symbol}，"
                        f"数量 {decision.intent.quantity}，限价 {decision.intent.limit_price}。"
                    ),
                    body=build_intraday_trade_email_body(decision),
                    artifacts=[
                        paths.paper_orders_log_path,
                        paths.paper_account_path,
                        paths.paper_positions_path,
                        paths.daily_usage_path,
                    ],
                    details={
                        "symbol": decision.intent.symbol,
                        "side": decision.intent.side,
                        "quantity": decision.intent.quantity,
                        "limit_price": decision.intent.limit_price,
                        "notional": round(decision.intent.quantity * decision.intent.limit_price, 2),
                        "confidence": decision.intent.confidence,
                        "reason_codes": list(decision.intent.reason_codes),
                    },
                )
        elif paper_result.status == "pending":
            decision = replace(decision, action_taken="paper_pending")
        elif paper_result.reason:
            decision.blocked_reasons.append(paper_result.reason)
    _append_intraday_rankings(agent_root, inputs, run_date=run_date)
    _append_policy_decision(agent_root, decision, run_date=run_date)
    _run_shadow_experiments_safely(agent_root, run_date, inputs, runtime.trading_mode, effective_risk_tier)
    return 0


def _run_shadow_experiments_safely(agent_root: Path, run_date: str, inputs, trading_mode: str, risk_tier: int) -> None:
    """Run active_shadow challengers over the champion's inputs. Best-effort: any failure
    here must never affect the champion run, so the whole block is swallowed."""
    try:
        from trading_agent.growth.experiment_queue import list_experiments

        if not list_experiments(agent_root, status="active_shadow"):
            return
        from trading_agent.growth.shadow_runner import run_active_shadow_experiments

        run_active_shadow_experiments(
            agent_root, run_date=run_date, champion_inputs=inputs,
            trading_mode=trading_mode, risk_tier=risk_tier,
        )
    except Exception:  # noqa: BLE001 - shadow experiments are never allowed to break champion intraday
        pass
