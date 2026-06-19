"""O1 weekly Serenity-skill stock screener (selection layer).

Discovers pool-external supply-chain bottleneck stocks (Codex + the vendored
``serenity-supply-chain`` skill), validates them with a strict price/volume factor gate,
and — only when ``ENABLE_WEEKLY_SCREENER=1`` — auto-updates ``universe.txt`` /
``universe_meta.json`` add-only (never deletes) + re-ranks. Selection layer only: it never
touches sizing, risk, trading mode, or order placement.

Built incrementally (O1 steps 1–4). Step 1 is the skeleton: config + dated run dir + a
status report. Later steps fill in discovery, factor validation, and the auto-apply writer.
"""

from trading_agent.screener.config import ScreenerConfig, load_screener_config
from trading_agent.screener.pipeline import run_screen

__all__ = ["ScreenerConfig", "load_screener_config", "run_screen"]
