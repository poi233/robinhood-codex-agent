from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class ScreenerConfig:
    """Resolved O1 weekly-screener knobs (user-locked defaults, 2026-06-19).

    All read from the environment so ``runtime.env`` / ``runtime.env.local`` / shell exports
    win in the usual precedence. ``enabled`` gates the only mutating behavior (writing the
    universe); everything else is just report generation.
    """

    enabled: bool
    max_adds_per_week: int
    universe_max: int
    min_dollar_volume: float
    require_uptrend: bool


def _read_int(env: Mapping[str, str], name: str, default: int) -> int:
    try:
        return int(env.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _read_float(env: Mapping[str, str], name: str, default: float) -> float:
    try:
        return float(env.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def load_screener_config(env: Mapping[str, str] | None = None) -> ScreenerConfig:
    env = env if env is not None else os.environ
    return ScreenerConfig(
        enabled=env.get("ENABLE_WEEKLY_SCREENER", "0") == "1",
        max_adds_per_week=_read_int(env, "SCREEN_MAX_ADDS_PER_WEEK", 5),
        universe_max=_read_int(env, "UNIVERSE_MAX", 120),
        min_dollar_volume=_read_float(env, "SCREEN_MIN_DOLLAR_VOL", 20_000_000.0),
        require_uptrend=env.get("SCREEN_REQUIRE_UPTREND", "1") == "1",
    )
