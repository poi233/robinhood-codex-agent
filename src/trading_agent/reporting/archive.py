from __future__ import annotations

from pathlib import Path

from trading_agent.core.io import ensure_dir, write_json


def write_premarket_archive_json(reports_root: Path, run_date: str, payload: dict[str, object]) -> Path:
    ensure_dir(reports_root / "premarket")
    output = reports_root / "premarket" / f"{run_date}.json"
    write_json(output, payload)
    return output
