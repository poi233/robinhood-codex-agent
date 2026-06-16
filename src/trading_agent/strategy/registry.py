from __future__ import annotations

import os
from pathlib import Path
from typing import Any


DEFAULT_STRATEGY: dict[str, Any] = {
    "strategy_id": "baseline_v1",
    "status": "active",
    "scoring_profile": "aggressive_growth",
    "policy_profile": "aggressive_growth",
    "watchlist": "active_watchlist.txt",
    "risk_tier_paper": 4,
    "risk_tier_live": 3,
    "parent": None,
    "change_reason": "strategy_registry.yaml missing; using built-in defaults",
}


def _parse_scalar(value: str) -> Any:
    raw = value.strip()
    if not raw or raw in ("null", "~"):
        return None
    if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
        return raw[1:-1]
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


def _parse_strategy_registry_yaml(path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {"strategies": {}}
    current_strategy: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line:
            continue
        stripped = line.strip()
        if stripped.startswith("active_strategy:"):
            payload["active_strategy"] = stripped.split(":", 1)[1].strip()
            continue
        if stripped == "strategies:":
            continue
        if line.startswith("  ") and not line.startswith("    ") and stripped.endswith(":"):
            current_strategy = stripped[:-1].strip()
            payload["strategies"][current_strategy] = {}
            continue
        if line.startswith("    ") and current_strategy and ":" in stripped:
            key, value = stripped.split(":", 1)
            payload["strategies"][current_strategy][key.strip()] = _parse_scalar(value)
    return payload


def list_strategy_ids(agent_root: Path) -> list[str]:
    """Return every strategy_id registered in strategy_registry.yaml (not just active)."""
    path = agent_root / "src" / "config" / "strategy_registry.yaml"
    if not path.exists():
        return [DEFAULT_STRATEGY["strategy_id"]]
    payload = _parse_strategy_registry_yaml(path)
    return list((payload.get("strategies") or {}).keys())


def load_active_strategy(agent_root: Path) -> dict[str, Any]:
    """Resolve the active strategy version registered in strategy_registry.yaml.

    Falls back to DEFAULT_STRATEGY (matching the values runtime.env hardcoded
    before this registry existed) if the file or the active entry is missing,
    so an unconfigured checkout behaves exactly as before.
    """
    path = agent_root / "src" / "config" / "strategy_registry.yaml"
    if not path.exists():
        return dict(DEFAULT_STRATEGY)
    payload = _parse_strategy_registry_yaml(path)
    strategies = payload.get("strategies") or {}
    active_id = str(payload.get("active_strategy") or DEFAULT_STRATEGY["strategy_id"])
    selected = strategies.get(active_id)
    if not isinstance(selected, dict):
        return dict(DEFAULT_STRATEGY)
    return {
        "strategy_id": active_id,
        "status": selected.get("status", "active"),
        "scoring_profile": selected.get("scoring_profile", DEFAULT_STRATEGY["scoring_profile"]),
        "policy_profile": selected.get("policy_profile", DEFAULT_STRATEGY["policy_profile"]),
        "watchlist": selected.get("watchlist", DEFAULT_STRATEGY["watchlist"]),
        "risk_tier_paper": int(selected.get("risk_tier_paper", DEFAULT_STRATEGY["risk_tier_paper"])),
        "risk_tier_live": int(selected.get("risk_tier_live", DEFAULT_STRATEGY["risk_tier_live"])),
        "parent": selected.get("parent"),
        "change_reason": selected.get("change_reason", ""),
    }


def apply_active_strategy_env_defaults(agent_root: Path) -> None:
    """Fill SCORING_PROFILE/POLICY_PROFILE/RISK_TIER/PAPER_RISK_TIER from the active
    strategy, but only for keys not already set.

    Shell exports and runtime.env/runtime.env.local always win; the registry is
    the lowest-priority default. This is what makes switching active_strategy
    in strategy_registry.yaml change the whole profile/tier combo at once.
    """
    strategy = load_active_strategy(agent_root)
    defaults = {
        "SCORING_PROFILE": str(strategy["scoring_profile"]),
        "POLICY_PROFILE": str(strategy["policy_profile"]),
        "RISK_TIER": str(strategy["risk_tier_live"]),
        "PAPER_RISK_TIER": str(strategy["risk_tier_paper"]),
    }
    for key, value in defaults.items():
        if key not in os.environ:
            os.environ[key] = value
