from __future__ import annotations

from trading_agent.growth.observations import GrowthContext, Observation

SETUP_RELATED_REASONS = ("outside_entry_zone", "chase_blocked", "reward_risk_too_low", "no_trade_zone")
DOMINANCE_PCT = 40.0


def diagnose(ctx: GrowthContext) -> list[Observation]:
    counts = ((ctx.replay.get("blocked_reasons") or {}).get("reason_counts") or {})
    total = sum(int(v) for v in counts.values())
    if total == 0:
        return []
    setup_block = sum(int(counts.get(r, 0)) for r in SETUP_RELATED_REASONS)
    pct = setup_block / total * 100
    if pct < DOMINANCE_PCT:
        return []
    return [
        Observation(
            "setup_gates_dominate_no_trades", "setups", "info",
            {
                "setup_block": setup_block,
                "total_blocks": total,
                "pct": round(pct, 1),
                "reasons": {r: int(counts.get(r, 0)) for r in SETUP_RELATED_REASONS if counts.get(r)},
            },
            "Entry/RR gates drive most no-trades; consider price_setup_weight / entry-tolerance experiments (paper).",
        )
    ]
