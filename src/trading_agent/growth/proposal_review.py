from __future__ import annotations

from pathlib import Path
from typing import Any

from trading_agent.core.io import read_json, write_json
from trading_agent.growth.policy import load_growth_policy
from trading_agent.growth.validator import validate_proposal


def _validation_path(proposal_path: Path) -> Path:
    return proposal_path.with_name(f"{proposal_path.stem}_validation.json")


def validate_proposal_file(agent_root: Path, proposal_path: Path) -> Path:
    """Validate one proposal JSON file against the agent's growth_policy and write a
    sibling ``<stem>_validation.json``. The original proposal file is never modified.
    Returns the validation file path. Fail-closed: a malformed file validates to rejected.
    """
    policy = load_growth_policy(agent_root)
    try:
        proposal = read_json(proposal_path)
    except (OSError, ValueError):
        proposal = {}
    if not isinstance(proposal, dict):
        proposal = {}
    result = validate_proposal(proposal, policy)
    out_path = _validation_path(proposal_path)
    write_json(out_path, result)
    return out_path


def validate_proposals_dir(agent_root: Path, proposals_dir: Path) -> list[Path]:
    """Validate every ``proposal_*.json`` (excluding ``*_validation.json``) in a dir."""
    written: list[Path] = []
    for path in sorted(proposals_dir.glob("proposal_*.json")):
        if path.name.endswith("_validation.json"):
            continue
        written.append(validate_proposal_file(agent_root, path))
    return written
