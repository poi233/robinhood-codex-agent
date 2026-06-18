from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from trading_agent.policy.candidate_selector import rank_candidates
from trading_agent.policy.advisory_overlay import overlay_for_symbol, symbol_overlay_to_dict
from trading_agent.policy.models import OrderIntent, PolicyInputs
from trading_agent.policy.price_policy import decide_buy_price
from trading_agent.policy.sizing_policy import decide_size


def _thesis_tags(inputs: PolicyInputs, symbol: str) -> list[str]:
    """K3: Derive thesis tags at trade time from DSA signals + universe_meta theme map.
    Tags are captured point-in-time so later attribution doesn't need to re-join DSA archives."""
    tags: list[str] = []
    sym_upper = symbol.upper()
    meta_theme = str(inputs.theme_map.get(sym_upper) or "").strip().upper().replace(" ", "_")
    if meta_theme:
        tags.append(meta_theme)
    sig = (((inputs.dsa_signals or {}).get("symbol_signals") or {}).get(sym_upper)
           or (inputs.dsa_signals or {}).get("symbol_signals", {}).get(symbol) or {})
    if isinstance(sig, dict):
        pt = str(sig.get("primary_theme") or "").strip().upper().replace(" ", "_")
        if pt and pt not in tags:
            tags.append(pt)
        for m in (sig.get("strategy_matches") or []):
            nm = str(m or "").strip().upper().replace(" ", "_")
            if nm and nm not in tags:
                tags.append(nm)
    return tags


@dataclass(frozen=True)
class BuyEvaluation:
    intent: OrderIntent | None
    blocked_reasons: list[str] = field(default_factory=list)
    # Per-candidate block reasons, keyed by symbol. Captured point-in-time so E3's richer near-miss
    # categories (outside_entry_zone / no_chase / reward_risk_too_low / …) can later be attributed to
    # the specific candidate that was gated, instead of only the run-level aggregate. Capture-now: if
    # we don't persist which symbol was blocked for which reason today, it can't be reconstructed.
    per_candidate_blocks: dict[str, list[str]] = field(default_factory=dict)


def _add_block(per_candidate: dict[str, list[str]], symbol: str, reason: str) -> None:
    bucket = per_candidate.setdefault(symbol, [])
    if reason and reason not in bucket:
        bucket.append(reason)


def evaluate_buy(inputs: PolicyInputs) -> BuyEvaluation:
    if not inputs.daily_plan:
        return BuyEvaluation(None, ["missing_daily_plan"])
    if inputs.daily_plan.get("market_regime") in {"risk_off", "no_trade"}:
        return BuyEvaluation(None, ["market_regime_blocks_buy"])
    if "small_limit_buy" not in inputs.daily_plan.get("allowed_actions", []):
        return BuyEvaluation(None, ["buy_not_allowed"])

    ranked, blocked = rank_candidates(inputs)
    # Selection-stage per-candidate blocks (score / regime / theme gates), captured for every symbol.
    per_candidate: dict[str, list[str]] = {}
    for symbol, reasons in blocked.items():
        for reason in reasons:
            _add_block(per_candidate, str(symbol).upper(), reason)

    if not ranked:
        blocked_reasons: list[str] = []
        for reasons in blocked.values():
            for reason in reasons:
                if reason not in blocked_reasons:
                    blocked_reasons.append(reason)
        return BuyEvaluation(None, blocked_reasons or ["no_buy_candidate"], per_candidate_blocks=per_candidate)

    blocked_reasons: list[str] = []
    for candidate in ranked:
        price = decide_buy_price(inputs, candidate)
        if price.blocked_reason:
            _add_block(per_candidate, candidate.symbol.upper(), price.blocked_reason)
            if price.blocked_reason not in blocked_reasons:
                blocked_reasons.append(price.blocked_reason)
            continue
        size = decide_size(inputs, candidate, price)
        if size.blocked_reason:
            _add_block(per_candidate, candidate.symbol.upper(), size.blocked_reason)
            if size.blocked_reason not in blocked_reasons:
                blocked_reasons.append(size.blocked_reason)
            continue

        return BuyEvaluation(
            OrderIntent(
                symbol=candidate.symbol,
                side="buy",
                order_type="limit",
                reference_price=inputs.quotes[candidate.symbol].price,
                bid=inputs.quotes[candidate.symbol].bid,
                ask=inputs.quotes[candidate.symbol].ask,
                spread_bps=inputs.quotes[candidate.symbol].spread_bps,
                advisory_overlay=symbol_overlay_to_dict(overlay_for_symbol(inputs.advisory_overlay, candidate.symbol)),
                thesis_tags=_thesis_tags(inputs, candidate.symbol),
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
            ),
            per_candidate_blocks=per_candidate,
        )

    return BuyEvaluation(None, blocked_reasons or ["no_buy_candidate"], per_candidate_blocks=per_candidate)
