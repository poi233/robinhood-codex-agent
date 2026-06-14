from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from trading_agent.core.config import load_runtime_config
from trading_agent.core.time import PT
from trading_agent.core.time import pt_date_string
from trading_agent.policy.engine import generate_order_intent
from trading_agent.policy.loaders import load_policy_inputs
from trading_agent.policy.models import PolicyDecision
from trading_agent.prompts.codex import run_codex_prompt


def _append_local_decision(agent_root: Path, decision: str, reason: str) -> None:
    log_path = agent_root / "logs" / "decisions.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": datetime.now(tz=PT).strftime("%Y-%m-%dT%H:%M:%S%z"),
        "run_kind": "intraday",
        "trading_mode": os.environ.get("TRADING_MODE", "paper"),
        "decision": decision,
        "action_taken": "none",
        "reason": reason,
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def _append_policy_decision(agent_root: Path, decision: PolicyDecision) -> None:
    log_path = agent_root / "logs" / "decisions.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    payload = decision.to_json_dict(timestamp=datetime.now(tz=PT).strftime("%Y-%m-%dT%H:%M:%S%z"))
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def _is_weekday_pt() -> bool:
    return datetime.now(tz=PT).weekday() < 5


def _is_intraday_window_pt() -> bool:
    now = datetime.now(tz=PT)
    current = now.hour * 60 + now.minute
    return 6 * 60 + 45 <= current <= 12 * 60 + 55


def run_intraday_pipeline(*, dry_run: bool) -> int:
    del dry_run
    agent_root = Path.cwd()
    if not _is_weekday_pt() and os.environ.get("ALLOW_WEEKEND_RUN", "0") != "1":
        _append_local_decision(agent_root, "calendar_skip", "not_a_weekday_pt")
        return 0
    if not _is_intraday_window_pt() and os.environ.get("ALLOW_OUTSIDE_MARKET_TEST", "0") != "1":
        _append_local_decision(agent_root, "time_window_skip", "outside_intraday_window_pt")
        return 0
    if (agent_root / "KILL_SWITCH").exists() and os.environ.get("ALLOW_KILL_SWITCH_PAPER_TEST", "0") != "1":
        _append_local_decision(agent_root, "kill_switch_skip", "KILL_SWITCH_present")
        return 0
    runtime = load_runtime_config(agent_root)
    inputs = load_policy_inputs(
        agent_root,
        run_date=pt_date_string(),
        trading_mode=runtime.trading_mode,
        risk_tier=runtime.risk_tier,
    )
    decision = generate_order_intent(inputs)
    _append_policy_decision(agent_root, decision)
    return 0
