from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import read_json
from trading_agent.data.universe import parse_universe
from trading_agent.prompts.codex import run_codex_prompt
from trading_agent.screener.paths import screener_run_dir

PromptRunner = Callable[..., int]

DEFAULT_DISCOVER_LIMIT = 25


def _read_existing_universe(config_dir: Path) -> list[str]:
    path = config_dir / "universe.txt"
    if not path.exists():
        return []
    try:
        return parse_universe(path)
    except Exception:
        return []


def _coerce_records(data: Any) -> list[Any]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("candidates", "discovered", "symbols"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []


def parse_discovered(path: Path, existing: set[str]) -> list[dict[str, Any]]:
    """Read the Codex-written discovery file, fail-closed.

    Missing/malformed file → empty list. Drops anything already in ``existing``, blanks, and
    duplicates. Accepts a bare list, ``{"candidates": [...]}``, or plain symbol strings.
    """
    if not path.exists():
        return []
    try:
        data = read_json(path)
    except Exception:
        return []

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in _coerce_records(data):
        if isinstance(row, str):
            symbol = row.strip().upper()
            record: dict[str, Any] = {"symbol": symbol}
        elif isinstance(row, dict):
            symbol = str(row.get("symbol") or row.get("ticker") or "").strip().upper()
            record = {**row, "symbol": symbol}
        else:
            continue
        if not symbol or symbol in existing or symbol in seen:
            continue
        seen.add(symbol)
        out.append(record)
    return out


def run_discovery(
    agent_root: Path,
    *,
    prompt_runner: PromptRunner = run_codex_prompt,
    limit: int | None = None,
) -> dict[str, Any]:
    """O1 step 3: run the Serenity discovery prompt and read back the (pool-external) candidates.

    Injects the output path + existing-universe exclusion list into the prompt via
    ``runtime_overrides`` (no change to the shared runtime block). When ``CODEX_EXEC_DRY_RUN=1``
    the prompt runner no-ops and no file is written, so discovery returns an empty list — exactly
    the fail-closed behavior the weekly cron needs when offline.
    """
    paths = build_runtime_paths(agent_root)
    run_dir = screener_run_dir(agent_root)
    run_dir.mkdir(parents=True, exist_ok=True)
    discovered_path = run_dir / "discovered.json"

    existing = _read_existing_universe(paths.config_dir)
    existing_set = set(existing)

    resolved_limit = limit if limit is not None else int(
        os.environ.get("SCREEN_DISCOVER_LIMIT", str(DEFAULT_DISCOVER_LIMIT)) or DEFAULT_DISCOVER_LIMIT
    )
    prompt_file = agent_root / "src" / "prompts" / "screener" / "discover.txt"

    overrides = {
        "DISCOVERED_PATH": str(discovered_path),
        "EXISTING_UNIVERSE_SYMBOLS": ",".join(existing),
        "EXISTING_UNIVERSE_COUNT": str(len(existing)),
        "SCREEN_DISCOVER_LIMIT": str(resolved_limit),
    }

    try:
        status = prompt_runner("screener_discover", agent_root, prompt_file, runtime_overrides=overrides)
    except FileNotFoundError:
        # No codex binary available (e.g. offline CI) → treat as a clean empty discovery.
        status = 127

    discovered = parse_discovered(discovered_path, existing_set)
    return {
        "status": status,
        "discovered_path": str(discovered_path),
        "existing_count": len(existing),
        "limit": resolved_limit,
        "discovered": discovered,
        "discovered_symbols": [r["symbol"] for r in discovered],
    }
