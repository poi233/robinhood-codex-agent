from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import read_json, write_json
from trading_agent.core.time import PT


def _read_json_or_none(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = read_json(path)
    return payload if isinstance(payload, dict) else None


def _is_market_closed(market_calendar: dict[str, Any] | None) -> bool:
    if not isinstance(market_calendar, dict):
        return False
    if market_calendar.get("trading_day") is False:
        return True
    session = str(market_calendar.get("session") or "").lower()
    return session in {"closed", "holiday", "weekend"}


def _raw_status_values(raw_status: dict[str, Any]) -> list[str]:
    values: list[str] = []
    direct = raw_status.get("data_status")
    if isinstance(direct, str):
        values.append(direct.lower())
    for value in raw_status.values():
        if isinstance(value, str) and value.lower() in {"ok", "partial", "failed", "missing", "stale"}:
            values.append(value.lower())
    return values


def normalize_layer_status(
    *,
    layer: str,
    raw_status: dict[str, Any] | None,
    market_calendar: dict[str, Any] | None,
) -> dict[str, Any]:
    if raw_status is None:
        return {
            "layer": layer,
            "status": "missing",
            "reason_code": "provider_failed",
            "execution_blocking": True,
            "research_blocking": True,
        }
    if not isinstance(raw_status, dict):
        return {
            "layer": layer,
            "status": "failed",
            "reason_code": "schema_invalid",
            "execution_blocking": True,
            "research_blocking": True,
        }

    values = _raw_status_values(raw_status)
    if "failed" in values:
        reason_code = "mcp_unavailable" if layer in {"account_snapshot", "robinhood_mcp"} else "provider_failed"
        return {
            "layer": layer,
            "status": "failed",
            "reason_code": reason_code,
            "execution_blocking": True,
            "research_blocking": True,
        }
    if "stale" in values or "missing" in values:
        return {
            "layer": layer,
            "status": "partial",
            "reason_code": "provider_partial",
            "execution_blocking": True,
            "research_blocking": False,
        }
    if "partial" in values:
        market_closed = _is_market_closed(market_calendar)
        return {
            "layer": layer,
            "status": "partial",
            "reason_code": "market_closed" if market_closed else "provider_partial",
            "execution_blocking": market_closed,
            "research_blocking": False,
        }

    return {
        "layer": layer,
        "status": "ok",
        "reason_code": "ok",
        "execution_blocking": False,
        "research_blocking": False,
    }


def build_data_status_summary(
    *,
    run_date: str,
    market_calendar: dict[str, Any] | None,
    layers: dict[str, dict[str, Any] | None],
) -> dict[str, Any]:
    normalized = {
        layer: normalize_layer_status(layer=layer, raw_status=raw_status, market_calendar=market_calendar)
        for layer, raw_status in layers.items()
    }
    reason_codes = [
        f"{layer}:{status['reason_code']}"
        for layer, status in normalized.items()
        if status.get("reason_code") != "ok"
    ]
    return {
        "date": run_date,
        "generated_at": datetime.now(tz=PT).isoformat(),
        "layers": normalized,
        "execution_blocking": any(bool(status.get("execution_blocking")) for status in normalized.values()),
        "research_blocking": any(bool(status.get("research_blocking")) for status in normalized.values()),
        "reason_codes": reason_codes,
    }


def build_data_status_summary_from_paths(agent_root: Path, run_date: str) -> dict[str, Any]:
    paths = build_runtime_paths(agent_root, run_date=run_date)
    market_calendar = _read_json_or_none(paths.market_calendar_path)
    summary = build_data_status_summary(
        run_date=run_date,
        market_calendar=market_calendar,
        layers={
            "account_snapshot": _read_json_or_none(paths.account_snapshot_path),
            "capital_snapshot": _read_json_or_none(paths.capital_snapshot_path),
            "market_calendar": market_calendar,
            "quote_snapshot_core": _read_json_or_none(paths.quote_snapshot_core_path),
            "dsa": _read_json_or_none(paths.dsa_signals_path),
            "kronos": _read_json_or_none(paths.kronos_signals_path),
            "technical": _read_json_or_none(paths.technical_signals_path),
            "candidate_snapshot": _read_json_or_none(paths.candidate_snapshot_path),
            "quote_snapshot_candidates": _read_json_or_none(paths.quote_snapshot_candidates_path),
            "tradability": _read_json_or_none(paths.tradability_snapshot_path),
            "catalyst": _read_json_or_none(paths.catalyst_snapshot_path),
            "trader_watch_levels": _read_json_or_none(paths.trader_watch_levels_path),
        },
    )
    write_json(paths.data_status_summary_path, summary)
    return summary

