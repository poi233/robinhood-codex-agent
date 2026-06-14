from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimeConfig:
    trading_mode: str
    codex_model: str
    risk_tier: int
    market_feed_timeframes: str


def load_runtime_config(agent_root: Path) -> RuntimeConfig:
    del agent_root
    env = os.environ
    return RuntimeConfig(
        trading_mode=env.get("TRADING_MODE", "paper"),
        codex_model=env.get("CODEX_MODEL", "gpt-5.5"),
        risk_tier=int(env.get("RISK_TIER", "0")),
        market_feed_timeframes=env.get("MARKET_FEED_TIMEFRAMES", "1w,1d,1h,15m"),
    )
