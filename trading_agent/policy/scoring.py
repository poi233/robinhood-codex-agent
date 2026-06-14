from __future__ import annotations

from trading_agent.policy.models import PolicyInputs


def score_symbol(inputs: PolicyInputs, symbol: str) -> int:
    symbol = symbol.upper()
    score = int(((inputs.dynamic_allowlist.get("symbol_scores") or {}).get(symbol) or {}).get("score", 0))

    dsa_symbol = ((inputs.dsa_signals.get("symbol_signals") or {}).get(symbol) or {})
    if dsa_symbol.get("suggested_premarket_use") == "block" or dsa_symbol.get("action") == "block":
        return 0

    research = inputs.research_reports.get(symbol) or {}
    risk_flags = {str(flag).lower() for flag in research.get("risk_flags", [])}
    if "block" in risk_flags or "high_confidence_negative_event" in risk_flags:
        return 0
    if research.get("research_bias") == "avoid":
        score = min(score, 50)

    return max(0, min(score, 100))
