from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Lifecycle states. Promotion to live is NEVER part of this machine — the terminal
# "promoted" state only means a human edited strategy_registry.yaml by hand (G8).
TERMINAL_STATES = {"promoted", "rejected", "archived"}
STATES = ["proposed", "human_approved", "active_shadow", "ready_for_review", *sorted(TERMINAL_STATES)]


class ExperimentTransitionError(RuntimeError):
    """Raised when a requested experiment state transition is not allowed."""


def _experiments_path(agent_root: Path) -> Path:
    return agent_root / "src" / "config" / "strategy_experiments.yaml"


def _parse_scalar(value: str) -> Any:
    raw = value.strip()
    if not raw or raw in ("null", "~"):
        return None
    if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
        return json.loads(raw)
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


def load_experiments(agent_root: Path) -> dict[str, dict[str, Any]]:
    """Read strategy_experiments.yaml into {experiment_id: {field: value}}. Empty if absent."""
    path = _experiments_path(agent_root)
    if not path.exists():
        return {}
    experiments: dict[str, dict[str, Any]] = {}
    current: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line:
            continue
        stripped = line.strip()
        if stripped == "experiments:":
            continue
        if line.startswith("  ") and not line.startswith("    ") and stripped.endswith(":"):
            current = stripped[:-1].strip()
            experiments[current] = {}
            continue
        if line.startswith("    ") and current and ":" in stripped:
            key, value = stripped.split(":", 1)
            experiments[current][key.strip()] = _parse_scalar(value)
    return experiments


def _format_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value))


# Stable field order keeps the YAML diff-friendly for human git review.
_FIELD_ORDER = [
    "status", "challenger_strategy_id", "parent_strategy_id", "module", "field",
    "current", "proposed", "proposal_id", "created_at", "updated_at",
]


def _write_experiments(agent_root: Path, experiments: dict[str, dict[str, Any]]) -> None:
    path = _experiments_path(agent_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Self-growth experiment queue (G5). Human-reviewed via git.",
        "# approve only enables shadow paper; it NEVER switches active_strategy.",
        "experiments:",
    ]
    for exp_id in sorted(experiments):
        record = experiments[exp_id]
        lines.append(f"  {exp_id}:")
        ordered_keys = [k for k in _FIELD_ORDER if k in record] + [k for k in record if k not in _FIELD_ORDER]
        for key in ordered_keys:
            lines.append(f"    {key}: {_format_scalar(record[key])}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def list_experiments(agent_root: Path, *, status: str | None = None) -> list[dict[str, Any]]:
    experiments = load_experiments(agent_root)
    rows = [{"experiment_id": exp_id, **record} for exp_id, record in sorted(experiments.items())]
    if status is not None:
        rows = [row for row in rows if row.get("status") == status]
    return rows


def add_experiment(
    agent_root: Path,
    proposal: dict[str, Any],
    *,
    parent_strategy_id: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Enqueue a proposal as a new experiment in the `proposed` state.

    Does not validate the proposal here (that is G4's job); this only records intent.
    The challenger never runs until a human runs `growth experiments approve`.
    """
    mutation = proposal.get("mutation") or {}
    module = str(mutation.get("module") or "")
    field = str(mutation.get("field") or "")
    proposed_value = mutation.get("proposed")
    created = created_at or datetime.now(timezone.utc).date().isoformat()
    experiment_id = f"exp_{created}_{module}_{field}"
    challenger_strategy_id = f"{parent_strategy_id}__{field}_{proposed_value}"
    record = {
        "status": "proposed",
        "challenger_strategy_id": challenger_strategy_id,
        "parent_strategy_id": parent_strategy_id,
        "module": module,
        "field": field,
        "current": mutation.get("current"),
        "proposed": proposed_value,
        "proposal_id": proposal.get("proposal_id"),
        "created_at": created,
        "updated_at": created,
    }
    experiments = load_experiments(agent_root)
    experiments[experiment_id] = record
    _write_experiments(agent_root, experiments)
    return {"experiment_id": experiment_id, **record}


def _transition(agent_root: Path, experiment_id: str, *, to_status: str, allowed_from: set[str]) -> dict[str, Any]:
    experiments = load_experiments(agent_root)
    if experiment_id not in experiments:
        raise KeyError(experiment_id)
    record = experiments[experiment_id]
    current = str(record.get("status") or "")
    if current not in allowed_from:
        raise ExperimentTransitionError(
            f"{experiment_id}: cannot move from {current!r} to {to_status!r} (allowed from {sorted(allowed_from)})"
        )
    record["status"] = to_status
    record["updated_at"] = datetime.now(timezone.utc).date().isoformat()
    _write_experiments(agent_root, experiments)
    return {"experiment_id": experiment_id, **record}


def approve_experiment(agent_root: Path, experiment_id: str) -> dict[str, Any]:
    """Human approval to start shadow paper. NEVER touches strategy_registry.yaml."""
    return _transition(agent_root, experiment_id, to_status="active_shadow", allowed_from={"proposed", "human_approved"})


def mark_ready_for_review(agent_root: Path, experiment_id: str) -> dict[str, Any]:
    return _transition(agent_root, experiment_id, to_status="ready_for_review", allowed_from={"active_shadow"})


def reject_experiment(agent_root: Path, experiment_id: str) -> dict[str, Any]:
    return _transition(
        agent_root, experiment_id, to_status="rejected",
        allowed_from={"proposed", "human_approved", "active_shadow", "ready_for_review"},
    )


def archive_experiment(agent_root: Path, experiment_id: str) -> dict[str, Any]:
    return _transition(
        agent_root, experiment_id, to_status="archived",
        allowed_from=set(STATES) - {"archived"},
    )
