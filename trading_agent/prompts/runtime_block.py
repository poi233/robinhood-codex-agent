from __future__ import annotations

import os
from pathlib import Path

from trading_agent.core.time import pt_date_string, pt_now


def build_runtime_block(run_kind: str, agent_root: Path) -> str:
    env = os.environ
    values = {
        "RUN_KIND": run_kind,
        "RUN_STARTED_AT": pt_now().strftime("%Y-%m-%dT%H:%M:%S%z"),
        "RUN_DATE_PT": pt_date_string(),
        "TIMEZONE": "America/Los_Angeles",
        "AGENT_ROOT": str(agent_root),
        "TRADING_MODE": env.get("TRADING_MODE", "paper"),
        "RISK_TIER": env.get("RISK_TIER", "0"),
        "KILL_SWITCH_STATUS": "present" if (agent_root / "KILL_SWITCH").exists() else "absent",
        "ALLOW_OUTSIDE_MARKET_TEST": env.get("ALLOW_OUTSIDE_MARKET_TEST", "0"),
        "MAX_SINGLE_ORDER_NOTIONAL": env.get("MAX_SINGLE_ORDER_NOTIONAL", "10"),
        "MAX_DAILY_NOTIONAL": env.get("MAX_DAILY_NOTIONAL", "25"),
        "CODEX_EXEC_DRY_RUN": env.get("CODEX_EXEC_DRY_RUN", "0"),
        "ENABLE_DSA_SIGNAL_LAYER": env.get("ENABLE_DSA_SIGNAL_LAYER", "1"),
        "ENABLE_MARKET_FEED_LAYER": env.get("ENABLE_MARKET_FEED_LAYER", "1"),
        "ENABLE_TECHNICAL_SIGNAL_LAYER": env.get("ENABLE_TECHNICAL_SIGNAL_LAYER", "1"),
        "MARKET_FEED_DIR": env.get("MARKET_FEED_DIR", str(agent_root / "state" / "market_feed" / pt_date_string())),
        "TECHNICAL_SIGNALS_PATH": env.get("TECHNICAL_SIGNALS_PATH", str(agent_root / "state" / "technical_signals.json")),
    }
    lines = ["<runtime>"]
    lines.extend(f"{key}={value}" for key, value in values.items())
    lines.append("</runtime>")
    lines.append("")
    return "\n".join(lines)
