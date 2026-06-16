from __future__ import annotations

import os
from pathlib import Path
from typing import Any


DEFAULT_SCORING_PROFILE = {
    "name": "aggressive_growth",
    "watchlist_threshold": 35.0,
    "trade_threshold": 50.0,
    "high_conviction_threshold": 80.0,
    "min_effective_coverage": 0.5,
    "max_scored_candidates": 20,
    "max_watchlist": 8,
    "max_tradable": 8,
    "max_theme_concentration_pct": 50.0,
    "max_speculative_theme_pct": 40.0,
    "speculative_theme_name": "speculative",
}


def _parse_scalar(value: str) -> str | float:
    raw = value.strip()
    if not raw:
        return ""
    try:
        return float(raw)
    except ValueError:
        return raw


def _parse_scoring_profiles_yaml(path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {"profiles": {}}
    current_profile: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line:
            continue
        stripped = line.strip()
        if stripped.startswith("default_profile:"):
            payload["default_profile"] = stripped.split(":", 1)[1].strip()
            continue
        if stripped == "profiles:":
            continue
        if not line.startswith(" ") and ":" in stripped:
            key, value = stripped.split(":", 1)
            payload[key.strip()] = _parse_scalar(value)
            continue
        if line.startswith("  ") and not line.startswith("    ") and stripped.endswith(":"):
            current_profile = stripped[:-1].strip()
            payload["profiles"][current_profile] = {}
            continue
        if line.startswith("    ") and current_profile and ":" in stripped:
            key, value = stripped.split(":", 1)
            payload["profiles"][current_profile][key.strip()] = _parse_scalar(value)
    return payload


def load_scoring_profile(config_dir: Path, *, profile_name: str | None = None) -> dict[str, Any]:
    path = config_dir / "scoring_profiles.yaml"
    if not path.exists():
        return dict(DEFAULT_SCORING_PROFILE)
    payload = _parse_scoring_profiles_yaml(path)
    profiles = payload.get("profiles") or {}
    default_name = str(payload.get("default_profile") or DEFAULT_SCORING_PROFILE["name"])
    requested_name = str(profile_name or os.environ.get("SCORING_PROFILE") or default_name)
    selected = profiles.get(requested_name) or profiles.get(default_name) or DEFAULT_SCORING_PROFILE
    resolved_name = (
        requested_name
        if requested_name in profiles
        else default_name
        if default_name in profiles
        else DEFAULT_SCORING_PROFILE["name"]
    )
    return {
        "name": resolved_name,
        "watchlist_threshold": float(selected.get("watchlist_threshold", DEFAULT_SCORING_PROFILE["watchlist_threshold"])),
        "trade_threshold": float(selected.get("trade_threshold", DEFAULT_SCORING_PROFILE["trade_threshold"])),
        "high_conviction_threshold": float(selected.get("high_conviction_threshold", DEFAULT_SCORING_PROFILE["high_conviction_threshold"])),
        "min_effective_coverage": float(selected.get("min_effective_coverage", DEFAULT_SCORING_PROFILE["min_effective_coverage"])),
        "max_scored_candidates": int(payload.get("max_scored_candidates", DEFAULT_SCORING_PROFILE["max_scored_candidates"])),
        "max_watchlist": int(payload.get("max_watchlist", DEFAULT_SCORING_PROFILE["max_watchlist"])),
        "max_tradable": int(payload.get("max_tradable", DEFAULT_SCORING_PROFILE["max_tradable"])),
        "max_theme_concentration_pct": float(payload.get("max_theme_concentration_pct", DEFAULT_SCORING_PROFILE["max_theme_concentration_pct"])),
        "max_speculative_theme_pct": float(payload.get("max_speculative_theme_pct", DEFAULT_SCORING_PROFILE["max_speculative_theme_pct"])),
        "speculative_theme_name": str(payload.get("speculative_theme_name", DEFAULT_SCORING_PROFILE["speculative_theme_name"])),
    }
