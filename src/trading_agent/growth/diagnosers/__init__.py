from __future__ import annotations

from typing import Any, Callable

from trading_agent.growth.diagnosers import scoring as _scoring
from trading_agent.growth.diagnosers import setups as _setups
from trading_agent.growth.observations import GrowthContext, Observation

Diagnoser = Callable[[GrowthContext], list[Observation]]

# Add a new module diagnoser by importing it and registering one entry here.
DIAGNOSERS: dict[str, Diagnoser] = {
    "scoring": _scoring.diagnose,
    "setups": _setups.diagnose,
}


def run_all(ctx: GrowthContext) -> dict[str, list[dict[str, Any]]]:
    """Run every registered diagnoser over the shared context (computed once)."""
    return {name: [o.to_dict() for o in fn(ctx)] for name, fn in DIAGNOSERS.items()}
