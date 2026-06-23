from __future__ import annotations

from trading_agent.policy.candidate_selector import RankedCandidate
from trading_agent.policy.models import PolicyInputs
from trading_agent.policy.setups import DEFAULT_SETUPS, SETUP_REGISTRY, BuyPriceDecision

# Re-exported so existing importers (e.g. sizing_policy) keep `from ...price_policy import BuyPriceDecision`.
__all__ = ["BuyPriceDecision", "decide_buy_price"]


def decide_buy_price(inputs: PolicyInputs, candidate: RankedCandidate) -> BuyPriceDecision:
    """Decide the entry price/levels for a candidate by trying the strategy's configured setups.

    The active strategy selects its entry logic via ``policy_profile["setups"]`` (an ordered list of
    names in ``setups.SETUP_REGISTRY``); the first setup that clears wins. The champion configures no
    ``setups`` key, so it falls back to ``DEFAULT_SETUPS`` (pullback → breakout) and is unchanged.
    When every setup blocks, the last block is returned (the setups all check no_trade_zone/chase
    first, so shared blocks surface consistently)."""
    profile = inputs.policy_profile or {}
    configured = profile.get("setups")
    setup_names = [str(name) for name in configured] if isinstance(configured, list) and configured else list(DEFAULT_SETUPS)

    last_blocked: BuyPriceDecision | None = None
    for name in setup_names:
        setup_fn = SETUP_REGISTRY.get(name)
        if setup_fn is None:
            continue
        decision = setup_fn(inputs, candidate)
        if decision.blocked_reason is None:
            return decision
        last_blocked = decision
    if last_blocked is not None:
        return last_blocked

    quote = inputs.quotes.get(candidate.symbol)
    price = quote.price if quote else 0.0
    return BuyPriceDecision("blocked", price, None, None, None, None, None, blocked_reason="no_setup_configured")
