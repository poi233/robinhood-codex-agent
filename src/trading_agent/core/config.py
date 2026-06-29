from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from trading_agent.strategy.registry import apply_active_strategy_env_defaults


PAPER_ONLY_RISK_TIER = 4


class TierMisconfigurationError(RuntimeError):
    """Raised when a paper-only risk tier would apply to a non-paper trading mode."""


@dataclass(frozen=True)
class RuntimeConfig:
    trading_mode: str
    codex_model: str       # reasoning-heavy / "thinking" model
    codex_model_mini: str  # simple data-fetch / formatting model
    risk_tier: int        # live / review tier
    paper_risk_tier: int  # paper-only tier (higher caps; let risk-budget & weight caps constrain)
    market_feed_timeframes: str

    @property
    def effective_risk_tier(self) -> int:
        """Return tier appropriate for the active trading_mode.

        Tier 4 (paper_max, $100k/$400k caps) is only safe to apply in paper
        mode. If trading_mode is live/review and risk_tier resolves to 4
        (e.g. an operator left RISK_TIER=4 set from prior paper testing),
        fail closed instead of handing real-money trades paper-sized caps.
        """
        if self.trading_mode != "paper" and self.risk_tier == PAPER_ONLY_RISK_TIER:
            raise TierMisconfigurationError(
                f"RISK_TIER={PAPER_ONLY_RISK_TIER} (paper_max) is not allowed when "
                f"TRADING_MODE={self.trading_mode!r}; this tier is paper-only."
            )
        return self.paper_risk_tier if self.trading_mode == "paper" else self.risk_tier


def load_env_files(agent_root: Path) -> None:
    """Parse runtime.env then runtime.env.local into os.environ.

    Values from local override base; neither overrides a key already
    present in the environment (shell exports remain highest priority).

    Call this before any skip-gate check (weekend/market-window/KILL_SWITCH
    allow-flags) so that overrides set only in runtime.env.local take effect
    on direct Python invocations, not just shell-wrapper runs that source the
    same files before exec'ing python.

    After the env files are merged in, also backfills SCORING_PROFILE/
    POLICY_PROFILE/RISK_TIER/PAPER_RISK_TIER from strategy_registry.yaml's
    active strategy (lowest priority — only fills keys still unset), so that
    switching active_strategy changes the whole profile/tier combo at once.
    """
    merged: dict[str, str] = {}
    for filename in ("runtime.env", "runtime.env.local"):
        path = agent_root / "src" / "config" / filename
        if not path.exists():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if key:
                merged[key] = value
    for key, value in merged.items():
        if key not in os.environ:
            os.environ[key] = value
    apply_active_strategy_env_defaults(agent_root)


def load_runtime_config(agent_root: Path) -> RuntimeConfig:
    load_env_files(agent_root)
    env = os.environ
    trading_mode = env.get("TRADING_MODE", "paper")
    risk_tier = int(env.get("RISK_TIER", "0"))
    paper_risk_tier = int(env.get("PAPER_RISK_TIER", str(risk_tier)))
    return RuntimeConfig(
        trading_mode=trading_mode,
        codex_model=env.get("CODEX_MODEL", "gpt-5.4"),
        codex_model_mini=env.get("CODEX_MODEL_MINI", "gpt-5.4"),
        risk_tier=risk_tier,
        paper_risk_tier=paper_risk_tier,
        market_feed_timeframes=env.get("MARKET_FEED_TIMEFRAMES", "1w,1d,1h,15m"),
    )
