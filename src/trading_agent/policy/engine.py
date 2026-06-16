from __future__ import annotations

from trading_agent.policy.buy import evaluate_buy
from trading_agent.policy.models import OrderIntent, PolicyDecision, PolicyInputs
from trading_agent.policy.sell import evaluate_sell


def _checked_symbols(inputs: PolicyInputs) -> list[str]:
    if inputs.daily_plan and isinstance(inputs.daily_plan.get("today_watchlist"), list):
        return [str(symbol).upper() for symbol in inputs.daily_plan["today_watchlist"]]
    return [str(symbol).upper() for symbol in inputs.today_allowlist or inputs.universe]


def generate_order_intent(inputs: PolicyInputs) -> PolicyDecision:
    checked_symbols = _checked_symbols(inputs)
    kill_switch_blocks = inputs.kill_switch_present and inputs.trading_mode != "paper"
    risk_checks: dict[str, bool | None] = {
        "kill_switch": not kill_switch_blocks,
        "daily_plan": inputs.daily_plan is not None,
        "trading_mode": inputs.trading_mode in {"paper", "review", "live"},
        "account_data": "buying_power" in inputs.account,
        "data_status": not bool((inputs.data_status_summary or {}).get("execution_blocking")),
        "risk_overlay": str((inputs.risk_overlay or {}).get("market_regime") or "").lower() not in {"no_trade", "risk_off"},
    }
    if kill_switch_blocks:
        return PolicyDecision(
            trading_mode=inputs.trading_mode,
            checked_symbols=checked_symbols,
            decision="blocked",
            reason="kill switch present",
            risk_checks=risk_checks,
            blocked_reasons=["kill_switch_present"],
        )
    if inputs.daily_plan is None:
        return PolicyDecision(
            trading_mode=inputs.trading_mode,
            checked_symbols=checked_symbols,
            decision="blocked",
            reason="missing daily plan",
            risk_checks=risk_checks,
            blocked_reasons=["missing_daily_plan"],
        )
    if str(inputs.daily_plan.get("date") or "") != inputs.run_date:
        return PolicyDecision(
            trading_mode=inputs.trading_mode,
            checked_symbols=checked_symbols,
            decision="blocked",
            reason="stale daily plan",
            risk_checks=risk_checks,
            blocked_reasons=["stale_daily_plan"],
        )
    if "buying_power" not in inputs.account:
        return PolicyDecision(
            trading_mode=inputs.trading_mode,
            checked_symbols=checked_symbols,
            decision="blocked",
            reason="missing account data",
            risk_checks=risk_checks,
            blocked_reasons=["missing_account"],
        )
    if (inputs.data_status_summary or {}).get("execution_blocking"):
        return PolicyDecision(
            trading_mode=inputs.trading_mode,
            checked_symbols=checked_symbols,
            decision="blocked",
            reason="execution blocked by data status",
            risk_checks=risk_checks,
            blocked_reasons=["data_status_blocked", *list((inputs.data_status_summary or {}).get("reason_codes") or [])],
        )
    if str((inputs.risk_overlay or {}).get("market_regime") or "").lower() in {"no_trade", "risk_off"}:
        return PolicyDecision(
            trading_mode=inputs.trading_mode,
            checked_symbols=checked_symbols,
            decision="blocked",
            reason="risk overlay blocks trading",
            risk_checks=risk_checks,
            blocked_reasons=["risk_overlay_blocks_trading", *list((inputs.risk_overlay or {}).get("no_trade_reasons") or [])],
        )

    intent: OrderIntent | None = evaluate_sell(inputs)
    buy_blocked_reasons: list[str] = []
    if intent is None:
        buy_evaluation = evaluate_buy(inputs)
        intent = buy_evaluation.intent
        buy_blocked_reasons = buy_evaluation.blocked_reasons
    if intent is None:
        hard_block_reasons = {
            "missing_quote",
            "stale_quote",
            "open_order_exists",
            "average_down_blocked",
            "allowlist_intersection_empty",
            "missing_daily_plan",
            "stale_daily_plan",
            "data_status_blocked",
            "risk_overlay_blocks_buy",
            "risk_overlay_blocks_trading",
            "research_invalid_condition",
            "missing_technical_levels",
            "no_trade_zone",
            "chase_blocked",
            "outside_entry_zone",
            "invalid_price_map",
            "reward_risk_too_low",
            "minimum_trade_notional_blocked",
            "risk_budget_exhausted",
            "profile_multiplier_blocked",
            "size_too_small",
            "cooldown_after_buy",
            "cooldown_after_stop",
            "daily_new_position_limit_reached",
            "weekly_new_position_limit_reached",
        }
        if any(reason in hard_block_reasons for reason in buy_blocked_reasons):
            return PolicyDecision(
                trading_mode=inputs.trading_mode,
                checked_symbols=checked_symbols,
                decision="blocked",
                reason=", ".join(buy_blocked_reasons),
                risk_checks={**risk_checks, "execution_wired": None},
                blocked_reasons=buy_blocked_reasons,
            )
        return PolicyDecision(
            trading_mode=inputs.trading_mode,
            checked_symbols=checked_symbols,
            decision="no_action",
            reason="no policy candidate passed",
            risk_checks={**risk_checks, "execution_wired": None},
        )

    if inputs.trading_mode in {"review", "live"}:
        return PolicyDecision(
            trading_mode=inputs.trading_mode,
            checked_symbols=checked_symbols,
            decision="blocked",
            intent=intent,
            reason="execution_not_wired",
            risk_checks={**risk_checks, "execution_wired": False},
            blocked_reasons=["execution_not_wired"],
        )

    return PolicyDecision(
        trading_mode=inputs.trading_mode,
        checked_symbols=checked_symbols,
        decision="would_trade",
        intent=intent,
        reason="policy buy intent generated",
        risk_checks={**risk_checks, "execution_wired": None},
    )
