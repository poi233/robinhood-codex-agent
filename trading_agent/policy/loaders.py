from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from trading_agent.data.universe import parse_universe
from trading_agent.policy.models import PolicyInputs


def _read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_allowlist(path: Path) -> list[str]:
    if not path.exists():
        return []
    symbols: list[str] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        candidate = line.split("#", 1)[0].strip().upper()
        if candidate and candidate not in seen:
            symbols.append(candidate)
            seen.add(candidate)
    return symbols


def _load_research_reports(root: Path, run_date: str) -> dict[str, dict[str, Any]]:
    report_dir = root / "state" / "research_reports" / run_date
    if not report_dir.exists():
        return {}
    reports: dict[str, dict[str, Any]] = {}
    for path in sorted(report_dir.glob("*.json")):
        payload = _read_json_if_exists(path)
        symbol = str(payload.get("symbol") or path.stem).upper()
        reports[symbol] = payload
    return reports


def load_policy_inputs(agent_root: Path, *, run_date: str, trading_mode: str, risk_tier: int) -> PolicyInputs:
    config_dir = agent_root / "config"
    state_dir = agent_root / "state"
    risk_tiers = _read_json_if_exists(config_dir / "risk_tiers.json")
    risk_caps = risk_tiers.get(str(risk_tier), {}) if isinstance(risk_tiers, dict) else {}
    daily_plan = _read_json_if_exists(state_dir / "daily_plan.json") or None

    return PolicyInputs(
        run_date=run_date,
        trading_mode=trading_mode,
        risk_tier=risk_tier,
        risk_caps=risk_caps,
        universe=parse_universe(config_dir / "universe.txt") if (config_dir / "universe.txt").exists() else [],
        today_allowlist=_read_allowlist(state_dir / "today_allowlist.txt"),
        daily_plan=daily_plan,
        dynamic_allowlist=_read_json_if_exists(state_dir / "dynamic_allowlist.json"),
        daily_usage=_read_json_if_exists(state_dir / "daily_usage.json"),
        dsa_signals=_read_json_if_exists(state_dir / "dsa_signals.json"),
        kronos_signals=_read_json_if_exists(state_dir / "kronos_signals.json"),
        technical_signals=_read_json_if_exists(state_dir / "technical_signals.json"),
        research_reports=_load_research_reports(agent_root, run_date),
        kill_switch_present=(agent_root / "KILL_SWITCH").exists(),
    )
