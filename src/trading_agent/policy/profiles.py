from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from trading_agent.core.io import read_json


DEFAULT_POLICY_PROFILE = "aggressive_growth"


def load_policy_profile(agent_root: Path) -> dict[str, Any]:
    profile_name = os.environ.get("POLICY_PROFILE", DEFAULT_POLICY_PROFILE)
    path = agent_root / "src" / "config" / "policy_profiles.json"
    if not path.exists():
        return {"name": profile_name, "enabled": False}
    payload = read_json(path)
    profiles = payload.get("profiles") if isinstance(payload, dict) else None
    if not isinstance(profiles, dict):
        return {"name": profile_name, "enabled": False}
    selected = profiles.get(profile_name) or {}
    if not isinstance(selected, dict):
        selected = {}
    return {"name": profile_name, **selected}
