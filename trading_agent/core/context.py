from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimePaths:
    agent_root: Path
    config_dir: Path
    scripts_dir: Path
    state_dir: Path
    logs_dir: Path
    reports_dir: Path


def build_runtime_paths(agent_root: Path) -> RuntimePaths:
    return RuntimePaths(
        agent_root=agent_root,
        config_dir=agent_root / "config",
        scripts_dir=agent_root / "scripts",
        state_dir=agent_root / "state",
        logs_dir=agent_root / "logs",
        reports_dir=agent_root / "reports",
    )
