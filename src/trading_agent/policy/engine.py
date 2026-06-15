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
    risk_checks: dict[str, bool | None] = {
        "daily_plan": inputs.daily_plan is not None,
        "trading_mode": inputs.trading_mode in {"paper", "review", "live"},
        "account_data": "buying_power" in inputs.account,
    }
    if inputs.daily_plan is None:
        return PolicyDecision(
            trading_mode=inputs.trading_mode,
            checked_symbols=checked_symbols,
            decision="blocked",
            reason="missing daily plan",
            risk_checks=risk_checks,
            blocked_reasons=["missing_daily_plan"],
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

    intent: OrderIntent | None = evaluate_sell(inputs)
    buy_blocked_reasons: list[str] = []
    if intent is None:
        buy_evaluation = evaluate_buy(inputs)
        intent = buy_evaluation.intent
        buy_blocked_reasons = buy_evaluation.blocked_reasons
    if intent is None:
        hard_block_reasons = {
            "score_below_threshold",
            "missing_quote",
            "open_order_exists",
            "daily_notional_exhausted",
            "single_order_notional_exhausted",
            "average_down_blocked",
            "allowlist_intersection_empty",
            "technical_entry_not_ready",
            "technical_size_too_small",
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
