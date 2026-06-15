from __future__ import annotations

from dataclasses import dataclass, field

from trading_agent.policy.candidate_selector import RankedCandidate
from trading_agent.policy.models import PolicyInputs
from trading_agent.policy.technical import as_float, price_in_zone


@dataclass(frozen=True)
class BuyPriceDecision:
    setup_type: str
    limit_price: float
    stop_price: float | None
    target_1: float | None
    target_2: float | None
    risk_per_share: float | None
    reward_risk: float | None
    reason_codes: list[str] = field(default_factory=list)
    blocked_reason: str | None = None


def decide_buy_price(inputs: PolicyInputs, candidate: RankedCandidate) -> BuyPriceDecision:
    symbol = candidate.symbol
    watch = ((inputs.trader_watch_levels.get("symbols") or {}).get(symbol) or {})
    quote = inputs.quotes[symbol]
    profile = inputs.policy_profile

    entry_low = as_float(watch.get("entry_low"))
    entry_high = as_float(watch.get("entry_high"))
    trigger_above = as_float(watch.get("buy_trigger_above"))
    do_not_chase_above = as_float(watch.get("do_not_chase_above"))
    no_trade_low = as_float(watch.get("no_trade_low"))
    no_trade_high = as_float(watch.get("no_trade_high"))
    stop_price = as_float(watch.get("invalidation_below"))
    target_1 = as_float(watch.get("target_1"))
    target_2 = as_float(watch.get("target_2"))

    if price_in_zone(quote.price, no_trade_low, no_trade_high):
        return BuyPriceDecision("blocked", quote.price, stop_price, target_1, target_2, None, None, blocked_reason="no_trade_zone")
    if do_not_chase_above is not None and quote.price > do_not_chase_above:
        return BuyPriceDecision("blocked", quote.price, stop_price, target_1, target_2, None, None, blocked_reason="chase_blocked")

    pullback_threshold = float(profile.get("pullback_score_threshold", 82))
    breakout_threshold = float(profile.get("breakout_score_threshold", 88))
    technical_min_score = float(profile.get("technical_min_score", 70))
    chase_tolerance = float(profile.get("breakout_chase_tolerance_pct", 0.002))

    in_entry = price_in_zone(quote.price, entry_low, entry_high)
    breakout = trigger_above is not None and quote.price >= trigger_above
    if in_entry and candidate.candidate_score >= pullback_threshold and candidate.technical_score >= technical_min_score:
        limit_price = min(quote.price, entry_high if entry_high is not None else quote.price)
        setup_type = "pullback"
        reason_codes = ["entry_zone_ok"]
    elif breakout and candidate.candidate_score >= breakout_threshold and candidate.technical_score >= technical_min_score:
        breakout_limit = trigger_above * (1.0 + chase_tolerance) if trigger_above is not None else quote.price
        if quote.price > breakout_limit:
            return BuyPriceDecision("blocked", quote.price, stop_price, target_1, target_2, None, None, blocked_reason="breakout_chase_tolerance_blocked")
        limit_price = min(quote.price, breakout_limit)
        setup_type = "breakout"
        reason_codes = ["breakout_trigger_ok"]
    else:
        return BuyPriceDecision("blocked", quote.price, stop_price, target_1, target_2, None, None, blocked_reason="outside_entry_zone")

    if stop_price is None or stop_price >= limit_price or target_1 is None or target_1 <= limit_price:
        return BuyPriceDecision("blocked", limit_price, stop_price, target_1, target_2, None, None, blocked_reason="invalid_price_map")

    risk_per_share = limit_price - stop_price
    reward_risk = (target_1 - limit_price) / risk_per_share if risk_per_share > 0 else None
    if reward_risk is None or reward_risk < float(profile.get("min_reward_risk", 1.5)):
        return BuyPriceDecision("blocked", limit_price, stop_price, target_1, target_2, risk_per_share, reward_risk, blocked_reason="reward_risk_too_low")

    return BuyPriceDecision(
        setup_type=setup_type,
        limit_price=round(limit_price, 4),
        stop_price=round(stop_price, 4),
        target_1=round(target_1, 4),
        target_2=round(target_2, 4) if target_2 is not None else None,
        risk_per_share=round(risk_per_share, 4),
        reward_risk=round(reward_risk, 4),
        reason_codes=[*reason_codes, "no_chase_ok", "reward_risk_ok"],
    )
