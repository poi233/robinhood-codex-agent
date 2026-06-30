from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from trading_agent.core.config import load_env_files, load_runtime_config
from trading_agent.core.context import build_runtime_paths, resolve_agent_root
from trading_agent.core.io import write_json
from trading_agent.core.time import PT
from trading_agent.core.time import pt_date_string
from trading_agent.data.live_quotes import fetch_yfinance_live_quotes
from trading_agent.notifications.email import send_trade_email_notification
from trading_agent.notifications.trade_email_reports import build_intraday_trade_email_body
from trading_agent.paper.broker import (
    apply_paper_intent,
    mark_paper_positions_to_market,
    reconcile_pending_paper_orders,
    record_paper_day_start,
)
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
    from trading_agent.policy.advisory_overlay import overlay_for_symbol, symbol_overlay_to_dict

    ranked, blocked = rank_candidates(inputs)
    if not ranked and not blocked:
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
                        "base_trade_readiness_score": candidate.base_trade_readiness_score,
                        "advisory_rank_delta": candidate.advisory_rank_delta,
                        "price_setup_score": candidate.price_setup_score,
                        "candidate_score": candidate.candidate_score,
                        "technical_score": candidate.technical_score,
                        "research_score": candidate.research_score,
                        "catalyst_score": candidate.catalyst_score,
                        "liquidity_score": candidate.liquidity_score,
                        "advisory_overlay": symbol_overlay_to_dict(
                            overlay_for_symbol(inputs.advisory_overlay, candidate.symbol)
                        ),
                    }
                )
                + "\n"
            )
        for symbol, reasons in sorted(blocked.items()):
            handle.write(
                json.dumps(
                    {
                        "timestamp": timestamp,
                        "run_date": run_date,
                        "symbol": symbol,
                        "blocked_reasons": list(reasons),
                        "advisory_overlay": symbol_overlay_to_dict(
                            overlay_for_symbol(inputs.advisory_overlay, symbol)
                        ),
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


def _maybe_capture_intraday_bars(agent_root: Path, run_date: str, inputs) -> None:
    """Q6: append this tick's per-symbol prices to intraday_bars.jsonl when ENABLE_INTRADAY_BAR_CAPTURE
    is on. Opt-in because it adds per-tick I/O to the hot path; best-effort so it never blocks trading.
    Flag off (default) → no-op, zero change to the existing path."""
    if os.environ.get("ENABLE_INTRADAY_BAR_CAPTURE", "0") != "1":
        return
    try:
        from trading_agent.data.intraday_bars import capture_intraday_bars

        capture_intraday_bars(agent_root, run_date=run_date, quotes=inputs.quotes)
    except Exception:
        pass


def run_intraday_pipeline(*, dry_run: bool) -> int:
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
    if runtime.trading_mode in {"review", "live"}:
        if dry_run:
            _append_local_decision(
                agent_root,
                "dry_run_skip",
                "dry_run_non_paper_prompt_skipped",
                run_date=run_date,
            )
            return 0
        # review/live use the SAME deterministic decision as paper; only execution
        # differs (a thin execute prompt places the exact engine-decided order).
        return _run_deterministic_nonpaper_intraday(
            agent_root, run_date=run_date, runtime=runtime, effective_risk_tier=effective_risk_tier
        )
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
        record_paper_day_start(
            agent_root,
            run_date=run_date,
            starting_cash=paper_starting_cash,
            quotes=inputs.quotes,
        )
        inputs = load_policy_inputs(
            agent_root,
            run_date=run_date,
            trading_mode=runtime.trading_mode,
            risk_tier=effective_risk_tier,
            robinhood_gateway=None,
            quote_provider=fetch_yfinance_live_quotes,
            require_live_quotes=True,
        )
        pending_fill_events = reconcile_pending_paper_orders(
            agent_root,
            run_date=run_date,
            quotes=inputs.quotes,
            starting_cash=paper_starting_cash,
        )
        mark_paper_positions_to_market(agent_root, run_date=run_date, quotes=inputs.quotes, event="intraday_mark")
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
    _maybe_capture_intraday_bars(agent_root, run_date, inputs)
    _run_shadow_experiments_safely(agent_root, run_date, inputs, runtime.trading_mode, effective_risk_tier)
    return 0


def _run_deterministic_nonpaper_intraday(
    agent_root: Path, *, run_date: str, runtime, effective_risk_tier: int
) -> int:
    """Review/live decision via the SAME deterministic engine as paper.

    Three phases, so the decision is identical to paper and only execution differs:
      1. snapshot prompt — read-only MCP fetch of fresh Agentic-account buying power,
         positions and open equity orders (no trading tools).
      2. decide — load_policy_inputs + generate_order_intent (same as paper).
      3. execute prompt — places EXACTLY the engine-decided order (LLM as executor
         only; no independent analysis). review → review_equity_order, live →
         place_equity_order, both still gated by .codex/config.toml + KILL_SWITCH.
    """
    paths = build_runtime_paths(agent_root, run_date=run_date)

    snap_status = run_codex_prompt("intraday_snapshot", agent_root, paths.prompts_dir / "intraday" / "snapshot.txt")
    if snap_status != 0:
        _append_local_decision(agent_root, "blocked", f"intraday_snapshot_failed:{snap_status}", run_date=run_date)
        return snap_status

    inputs = load_policy_inputs(
        agent_root,
        run_date=run_date,
        trading_mode=runtime.trading_mode,
        risk_tier=effective_risk_tier,
        robinhood_gateway=None,
        quote_provider=fetch_yfinance_live_quotes,
        require_live_quotes=True,
    )
    decision = generate_order_intent(inputs)

    if decision.decision == "would_trade" and decision.intent is not None:
        order_path = paths.run_state_dir / "intraday_execute_order.json"
        order_payload = {**decision.intent.to_json_dict(), "run_date": run_date}
        write_json(order_path, order_payload)
        exec_status = run_codex_prompt(
            "intraday_execute",
            agent_root,
            paths.prompts_dir / "intraday" / "execute.txt",
            runtime_overrides={
                "EXECUTE_ORDER_PATH": str(order_path),
                "EXECUTE_MODE": runtime.trading_mode,
            },
        )
        if exec_status == 0:
            decision = replace(
                decision,
                action_taken="live_order_submitted" if runtime.trading_mode == "live" else "review_submitted",
            )
        else:
            decision = replace(
                decision,
                action_taken="execute_failed",
                blocked_reasons=[*decision.blocked_reasons, f"execute_prompt_failed:{exec_status}"],
            )

    _append_intraday_rankings(agent_root, inputs, run_date=run_date)
    _append_policy_decision(agent_root, decision, run_date=run_date)
    _maybe_capture_intraday_bars(agent_root, run_date, inputs)
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
