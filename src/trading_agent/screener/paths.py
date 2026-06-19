from __future__ import annotations

from pathlib import Path

from trading_agent.core.context import build_runtime_paths


def screener_run_dir(agent_root: Path, *, run_date: str | None = None) -> Path:
    """Dated screener output dir: ``runtime/screener/<date>/``.

    Holds the weekly run's artifacts (status, discovered candidates, universe backup, and the
    universe_change audit). Kept under git-ignored ``runtime/`` like all other generated state.
    """
    paths = build_runtime_paths(agent_root, run_date=run_date)
    return paths.runtime_dir / "screener" / paths.run_date
