"""Pluggable intraday entry setups (the buy-side price gate).

`decide_buy_price` (price_policy.py) is a thin dispatcher over this registry. Each setup is a
pure function ``(inputs, candidate) -> BuyPriceDecision`` that decides — from premarket levels and
the live quote — whether/where to enter, or returns a ``blocked_reason``. A strategy chooses which
setups it runs (and in what order) via ``policy_profile["setups"]``; the champion configures none,
so it falls back to ``DEFAULT_SETUPS`` (``pullback`` + ``breakout``) and behaves exactly as before.

Why this exists: the champion's pullback/breakout setups only ever fire when premarket emitted a
*valid* ``long_setup`` with a real entry zone, which `signals.technical_engine._build_setups` only
does for bullish + (breakout|pullback) symbols (otherwise the entry zone collapses to a single price
and the no-trade zone covers the whole range). The alternative setups below instead derive entries
from the **always-present** ``key_levels`` (reference_price / supports / resistances / range), so
challenger strategies actually trade on days the champion is silent — in isolated paper ledgers, for
comparison only. Every setup still enforces the same hard safety: a valid price map (stop < limit <
target) and ``min_reward_risk``; sizing/hard-stop/per-trade-risk gates run downstream as usual.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from trading_agent.policy.candidate_selector import RankedCandidate
from trading_agent.policy.models import PolicyInputs
from trading_agent.policy.technical import as_float, price_in_zone


# The champion's setup stack. Kept byte-for-byte equivalent to the pre-dispatcher decide_buy_price.
DEFAULT_SETUPS: tuple[str, ...] = ("pullback", "breakout")


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


# --------------------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------------------

def _watch(inputs: PolicyInputs, symbol: str) -> dict:
    return ((inputs.trader_watch_levels.get("symbols") or {}).get(symbol) or {})


def _level_list(watch: dict, key: str) -> list[float]:
    raw = watch.get(key)
    if not isinstance(raw, list):
        return []
    out: list[float] = []
    for value in raw:
        f = as_float(value)
        if f is not None and f > 0:
            out.append(f)
    return out


def _support_1(watch: dict) -> float | None:
    supports = _level_list(watch, "supports")
    if supports:
        return max(supports)  # nearest support below price = the highest one
    return as_float(watch.get("range_low"))


def _resistances_above(watch: dict, price: float) -> list[float]:
    levels = _level_list(watch, "resistances")
    rng_high = as_float(watch.get("range_high"))
    if rng_high is not None:
        levels.append(rng_high)
    return sorted({lvl for lvl in levels if lvl > price})


def _blocked(symbol_price: float, reason: str, *, setup_type: str = "blocked") -> BuyPriceDecision:
    return BuyPriceDecision(setup_type, symbol_price, None, None, None, None, None, blocked_reason=reason)


def _finalize(
    profile: dict,
    *,
    setup_type: str,
    limit_price: float,
    stop_price: float | None,
    target_1: float | None,
    target_2: float | None,
    reason_codes: list[str],
) -> BuyPriceDecision:
    """Shared price-map + reward:risk gate. Identical to the champion's original tail, so the
    pullback/breakout setups produce byte-for-byte the same decisions as before the refactor."""
    if stop_price is None or stop_price >= limit_price or target_1 is None or target_1 <= limit_price:
        return BuyPriceDecision(
            "blocked", limit_price, stop_price, target_1, target_2, None, None,
            blocked_reason="invalid_price_map",
        )
    risk_per_share = limit_price - stop_price
    reward_risk = (target_1 - limit_price) / risk_per_share if risk_per_share > 0 else None
    if reward_risk is None or reward_risk < float(profile.get("min_reward_risk", 1.5)):
        return BuyPriceDecision(
            "blocked", limit_price, stop_price, target_1, target_2, risk_per_share, reward_risk,
            blocked_reason="reward_risk_too_low",
        )
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


# --------------------------------------------------------------------------------------
# Champion setups (moved verbatim from price_policy.decide_buy_price)
# --------------------------------------------------------------------------------------

def setup_pullback(inputs: PolicyInputs, candidate: RankedCandidate) -> BuyPriceDecision:
    symbol = candidate.symbol
    watch = _watch(inputs, symbol)
    quote = inputs.quotes[symbol]
    profile = inputs.policy_profile or {}

    entry_low = as_float(watch.get("entry_low"))
    entry_high = as_float(watch.get("entry_high"))
    do_not_chase_above = as_float(watch.get("do_not_chase_above"))
    no_trade_low = as_float(watch.get("no_trade_low"))
    no_trade_high = as_float(watch.get("no_trade_high"))
    stop_price = as_float(watch.get("invalidation_below"))
    target_1 = as_float(watch.get("target_1"))
    target_2 = as_float(watch.get("target_2"))

    if price_in_zone(quote.price, no_trade_low, no_trade_high):
        return _blocked(quote.price, "no_trade_zone")
    if do_not_chase_above is not None and quote.price > do_not_chase_above:
        return _blocked(quote.price, "chase_blocked")

    pullback_threshold = float(profile.get("pullback_score_threshold", 82))
    technical_min_score = float(profile.get("technical_min_score", 70))
    in_entry = price_in_zone(quote.price, entry_low, entry_high)
    if not (in_entry and candidate.candidate_score >= pullback_threshold and candidate.technical_score >= technical_min_score):
        return _blocked(quote.price, "outside_entry_zone")
    limit_price = min(quote.price, entry_high if entry_high is not None else quote.price)
    return _finalize(
        profile, setup_type="pullback", limit_price=limit_price,
        stop_price=stop_price, target_1=target_1, target_2=target_2, reason_codes=["entry_zone_ok"],
    )


def setup_breakout(inputs: PolicyInputs, candidate: RankedCandidate) -> BuyPriceDecision:
    symbol = candidate.symbol
    watch = _watch(inputs, symbol)
    quote = inputs.quotes[symbol]
    profile = inputs.policy_profile or {}

    trigger_above = as_float(watch.get("buy_trigger_above"))
    do_not_chase_above = as_float(watch.get("do_not_chase_above"))
    no_trade_low = as_float(watch.get("no_trade_low"))
    no_trade_high = as_float(watch.get("no_trade_high"))
    stop_price = as_float(watch.get("invalidation_below"))
    target_1 = as_float(watch.get("target_1"))
    target_2 = as_float(watch.get("target_2"))

    if price_in_zone(quote.price, no_trade_low, no_trade_high):
        return _blocked(quote.price, "no_trade_zone")
    if do_not_chase_above is not None and quote.price > do_not_chase_above:
        return _blocked(quote.price, "chase_blocked")

    breakout_threshold = float(profile.get("breakout_score_threshold", 88))
    technical_min_score = float(profile.get("technical_min_score", 70))
    chase_tolerance = float(profile.get("breakout_chase_tolerance_pct", 0.002))
    breakout = trigger_above is not None and quote.price >= trigger_above
    if not (breakout and candidate.candidate_score >= breakout_threshold and candidate.technical_score >= technical_min_score):
        return _blocked(quote.price, "outside_entry_zone")
    breakout_limit = trigger_above * (1.0 + chase_tolerance) if trigger_above is not None else quote.price
    if quote.price > breakout_limit:
        return _blocked(quote.price, "breakout_chase_tolerance_blocked")
    limit_price = min(quote.price, breakout_limit)
    return _finalize(
        profile, setup_type="breakout", limit_price=limit_price,
        stop_price=stop_price, target_1=target_1, target_2=target_2, reason_codes=["breakout_trigger_ok"],
    )


# --------------------------------------------------------------------------------------
# Alternative setups (challenger strategies; derive entries from always-present key_levels)
# --------------------------------------------------------------------------------------

def _tightest_stop(limit: float, *levels: float | None) -> float | None:
    """The tightest (highest) provided level strictly below limit, or None if none qualify.
    Tighter stop → smaller risk → the reward:risk gate passes more often and per-trade-risk sizing
    sizes up accordingly. Each setup chooses which structural levels (and any %-stop) to offer."""
    below = [lvl for lvl in levels if lvl is not None and 0 < lvl < limit]
    return max(below) if below else None


def _fallback_targets(limit: float, profile: dict, candidates: list[float]) -> tuple[float | None, float | None]:
    above = sorted({lvl for lvl in candidates if lvl is not None and lvl > limit})
    if above:
        target_1 = above[0]
        target_2 = above[1] if len(above) > 1 else None
        return target_1, target_2
    pct = float(profile.get("target_fallback_pct", 0.05))
    if pct <= 0:
        return None, None
    return limit * (1.0 + pct), limit * (1.0 + 2.0 * pct)


def setup_breakout_momentum(inputs: PolicyInputs, candidate: RankedCandidate) -> BuyPriceDecision:
    """Buy strength as price clears the nearest resistance / range high, with a wider chase
    tolerance than the champion breakout and a lower score bar. Uses raw key_levels (not the
    long_setup entry zone or its do_not_chase line, which collapse for non-bullish symbols)."""
    symbol = candidate.symbol
    watch = _watch(inputs, symbol)
    quote = inputs.quotes.get(symbol)
    profile = inputs.policy_profile or {}
    if not quote or quote.price <= 0:
        return _blocked(0.0, "missing_quote")
    price = quote.price

    resistances = sorted(set(_level_list(watch, "resistances")))
    range_high = as_float(watch.get("range_high"))
    trigger = next((lvl for lvl in resistances if lvl <= price), None)
    if trigger is None and range_high is not None and price >= range_high:
        trigger = range_high
    if trigger is None:
        return _blocked(price, "below_breakout_trigger")

    tolerance = float(profile.get("breakout_chase_tolerance_pct", 0.01))
    ceiling = trigger * (1.0 + tolerance)
    if price > ceiling:
        return _blocked(price, "breakout_chase_tolerance_blocked")
    if candidate.candidate_score < float(profile.get("breakout_score_threshold", 60)):
        return _blocked(price, "score_below_threshold")

    limit_price = min(price, ceiling)
    # Breakout-failure stop: just below the level we broke (structural), with support as a fallback.
    stop_buffer = float(profile.get("momentum_stop_buffer_pct", 0.01))
    stop_price = _tightest_stop(limit_price, trigger * (1.0 - stop_buffer), _support_1(watch))
    target_1, target_2 = _fallback_targets(
        limit_price, profile, [lvl for lvl in resistances if lvl > limit_price] + [range_high],
    )
    return _finalize(
        profile, setup_type="breakout_momentum", limit_price=limit_price,
        stop_price=stop_price, target_1=target_1, target_2=target_2, reason_codes=["momentum_breakout_ok"],
    )


def setup_trend_continuation(inputs: PolicyInputs, candidate: RankedCandidate) -> BuyPriceDecision:
    """Buy an established uptrend on any mild advance above the reference price (not extended),
    without requiring the narrow premarket entry zone. Skips clearly bearish research bias."""
    symbol = candidate.symbol
    watch = _watch(inputs, symbol)
    quote = inputs.quotes.get(symbol)
    profile = inputs.policy_profile or {}
    if not quote or quote.price <= 0:
        return _blocked(0.0, "missing_quote")
    price = quote.price

    reference = as_float(watch.get("reference_price")) or as_float(watch.get("range_low"))
    if reference is None:
        return _blocked(price, "missing_reference")
    if price < reference:
        return _blocked(price, "below_trend_reference")
    extension_max = float(profile.get("trend_extension_max_pct", 0.05))
    if price > reference * (1.0 + extension_max):
        return _blocked(price, "trend_extended")
    research = inputs.research_reports.get(symbol) or {}
    if str(research.get("research_bias") or "").lower() in {"cautious", "avoid"}:
        return _blocked(price, "research_bias_blocks_trend")
    if candidate.candidate_score < float(profile.get("trend_score_threshold", 55)):
        return _blocked(price, "score_below_threshold")

    limit_price = price
    # Mid-trend entry: stop at the tighter of nearest support or a %-stop, so risk stays bounded
    # and reward:risk to the next resistance can clear.
    pct_stop = limit_price * (1.0 - float(profile.get("stop_fallback_pct", 0.03)))
    stop_price = _tightest_stop(limit_price, _support_1(watch), pct_stop)
    target_1, target_2 = _fallback_targets(
        limit_price, profile, _resistances_above(watch, limit_price),
    )
    return _finalize(
        profile, setup_type="trend_continuation", limit_price=limit_price,
        stop_price=stop_price, target_1=target_1, target_2=target_2, reason_codes=["trend_continuation_ok"],
    )


def setup_dip_pullback(inputs: PolicyInputs, candidate: RankedCandidate) -> BuyPriceDecision:
    """Buy a controlled pullback toward the nearest support (a band just above support_1), even
    when premarket only marked the long setup 'watch'. Refuses to catch a falling knife: price must
    stay above support (the stop), not below it."""
    symbol = candidate.symbol
    watch = _watch(inputs, symbol)
    quote = inputs.quotes.get(symbol)
    profile = inputs.policy_profile or {}
    if not quote or quote.price <= 0:
        return _blocked(0.0, "missing_quote")
    price = quote.price

    support = _support_1(watch)
    if support is None or support <= 0:
        return _blocked(price, "missing_support")
    if price <= support:
        return _blocked(price, "below_support")
    band_pct = float(profile.get("dip_band_pct", 0.03))
    if price > support * (1.0 + band_pct):
        return _blocked(price, "outside_dip_band")
    if candidate.candidate_score < float(profile.get("pullback_score_threshold", 55)):
        return _blocked(price, "score_below_threshold")

    limit_price = price
    # Structural stop just below the support we are buying against; targets are the resistances above.
    stop_price = _tightest_stop(limit_price, support * (1.0 - float(profile.get("dip_stop_buffer_pct", 0.01))))
    target_1, target_2 = _fallback_targets(limit_price, profile, _resistances_above(watch, limit_price))
    return _finalize(
        profile, setup_type="dip_pullback", limit_price=limit_price,
        stop_price=stop_price, target_1=target_1, target_2=target_2, reason_codes=["dip_pullback_ok"],
    )


def setup_range_reversion(inputs: PolicyInputs, candidate: RankedCandidate) -> BuyPriceDecision:
    """Mean-revert inside an established range: buy near range_low/support, target range_high/
    resistance, stop just below the range floor. Only fires when a real range exists and price sits
    in its lower portion — so it trades the chop the champion's no_trade_zone deliberately skips."""
    symbol = candidate.symbol
    watch = _watch(inputs, symbol)
    quote = inputs.quotes.get(symbol)
    profile = inputs.policy_profile or {}
    if not quote or quote.price <= 0:
        return _blocked(0.0, "missing_quote")
    price = quote.price

    range_low = as_float(watch.get("range_low")) or _support_1(watch)
    range_high = as_float(watch.get("range_high"))
    if range_low is None or range_high is None or range_high <= range_low:
        return _blocked(price, "no_established_range")
    if not (range_low < price < range_high):
        return _blocked(price, "outside_range")
    # Only buy the lower portion of the range (default lower 40%).
    lower_frac = float(profile.get("range_lower_fraction", 0.4))
    buy_ceiling = range_low + lower_frac * (range_high - range_low)
    if price > buy_ceiling:
        return _blocked(price, "above_range_buy_zone")
    if candidate.candidate_score < float(profile.get("range_score_threshold", 50)):
        return _blocked(price, "score_below_threshold")

    limit_price = price
    # Structural stop just below the range floor (a clean range break invalidates the reversion).
    floor_buffer = float(profile.get("range_stop_buffer_pct", 0.01))
    stop_price = _tightest_stop(limit_price, range_low * (1.0 - floor_buffer))
    resistance_1 = next(iter(_resistances_above(watch, limit_price)), None)
    target_1, target_2 = _fallback_targets(
        limit_price, profile, [lvl for lvl in (resistance_1, range_high) if lvl is not None],
    )
    return _finalize(
        profile, setup_type="range_reversion", limit_price=limit_price,
        stop_price=stop_price, target_1=target_1, target_2=target_2, reason_codes=["range_reversion_ok"],
    )


SETUP_REGISTRY: dict[str, Callable[[PolicyInputs, RankedCandidate], BuyPriceDecision]] = {
    "pullback": setup_pullback,
    "breakout": setup_breakout,
    "breakout_momentum": setup_breakout_momentum,
    "trend_continuation": setup_trend_continuation,
    "dip_pullback": setup_dip_pullback,
    "range_reversion": setup_range_reversion,
}
