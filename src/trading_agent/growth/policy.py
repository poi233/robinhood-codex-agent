from __future__ import annotations

from pathlib import Path
from typing import Any

from trading_agent.core.io import read_json

# Hard safety defaults. The forbidden list here can never be narrowed by config;
# load_growth_policy always unions these back in.
DEFAULT_GROWTH_POLICY: dict[str, Any] = {
    "enabled": False,
    "mode": "paper_only",
    "proposal": {
        "max_new_proposals_per_week": 2,
        "min_days_between_proposals": 5,
        "require_human_approval": True,
    },
    "allowed_mutations": {},
    "forbidden_mutations": [
        "TRADING_MODE", "RISK_TIER", "PAPER_RISK_TIER", "KILL_SWITCH",
        "MCP_APPROVAL", "place_equity_order", "per_trade_risk_pct",
        "max_daily_risk_pct", "max_single_stock_weight",
    ],
    "promotion_rules": {},
}


def load_growth_policy(agent_root: Path) -> dict[str, Any]:
    """Load src/config/growth_policy.json merged over safe defaults.

    The forbidden_mutations list is treated as union-only: whatever the file
    says, the hard defaults are always added back, so a tampered or partial
    config can widen the deny-list but never weaken it.
    """
    path = agent_root / "src" / "config" / "growth_policy.json"
    if not path.exists():
        return _with_forbidden_defaults(dict(DEFAULT_GROWTH_POLICY))
    payload = read_json(path)
    if not isinstance(payload, dict):
        return _with_forbidden_defaults(dict(DEFAULT_GROWTH_POLICY))
    merged = {**DEFAULT_GROWTH_POLICY, **payload}
    return _with_forbidden_defaults(merged, payload.get("forbidden_mutations"))


def _with_forbidden_defaults(policy: dict[str, Any], extra: Any = None) -> dict[str, Any]:
    forbidden = set(DEFAULT_GROWTH_POLICY["forbidden_mutations"])
    if isinstance(extra, list):
        forbidden.update(str(item) for item in extra)
    else:
        forbidden.update(policy.get("forbidden_mutations") or [])
    policy["forbidden_mutations"] = sorted(forbidden)
    return policy
