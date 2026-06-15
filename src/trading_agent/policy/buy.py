from __future__ import annotations

from dataclasses import dataclass, field

from trading_agent.policy.candidate_selector import rank_candidates
from trading_agent.policy.models import OrderIntent, PolicyInputs
from trading_agent.policy.price_policy import decide_buy_price
from trading_agent.policy.sizing_policy import decide_size


@dataclass(frozen=True)
class BuyEvaluation:
    intent: OrderIntent | None
    blocked_reasons: list[str] = field(default_factory=list)


def evaluate_buy(inputs: PolicyInputs) -> BuyEvaluation:
    if not inputs.daily_plan:
        return BuyEvaluation(None, ["missing_daily_plan"])
    if inputs.daily_plan.get("market_regime") in {"risk_off", "no_trade"}:
        return BuyEvaluation(None, ["market_regime_blocks_buy"])
    if "small_limit_buy" not in inputs.daily_plan.get("allowed_actions", []):
        return BuyEvaluation(None, ["buy_not_allowed"])

    ranked, blocked = rank_candidates(inputs)
    if not ranked:
        blocked_reasons: list[str] = []
        for reasons in blocked.values():
            for reason in reasons:
                if reason not in blocked_reasons:
                    blocked_reasons.append(reason)
        return BuyEvaluation(None, blocked_reasons or ["no_buy_candidate"])

    blocked_reasons: list[str] = []
    for candidate in ranked:
        price = decide_buy_price(inputs, candidate)
        if price.blocked_reason:
            if price.blocked_reason not in blocked_reasons:
                blocked_reasons.append(price.blocked_reason)
            continue
        size = decide_size(inputs, candidate, price)
        if size.blocked_reason:
            if size.blocked_reason not in blocked_reasons:
                blocked_reasons.append(size.blocked_reason)
            continue

        return BuyEvaluation(
            OrderIntent(
                symbol=candidate.symbol,
                side="buy",
                order_type="limit",
                reference_price=inputs.quotes[candidate.symbol].price,
                setup_type=price.setup_type,
                limit_price=price.limit_price,
                estimated_notional=size.estimated_notional,
                quantity=size.quantity,
                stop_price=price.stop_price,
                target_1=price.target_1,
                target_2=price.target_2,
                reward_risk=price.reward_risk,
                reason_codes=[
                    "candidate_score_pass",
                    "technical_component_pass",
                    *candidate.reason_codes,
                    *price.reason_codes,
                    *size.reason_codes,
                ],
                confidence=min(0.99, candidate.trade_readiness_score / 100),
            )
        )

    return BuyEvaluation(None, blocked_reasons or ["no_buy_candidate"])
