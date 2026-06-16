from __future__ import annotations

from typing import Any

_EPS = 1e-9


def validate_mutation(mutation: dict[str, Any], policy: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate one proposed mutation against growth_policy. Fail-closed.

    mutation shapes:
      scalar: {"module": "scoring", "field": "trade_threshold", "current": 50, "proposed": 56}
      weights: {"module": "scoring", "field": "component_weights",
                "current_weights": {...}, "proposed_weights": {...}}

    Returns (ok, violations). Any unknown field, forbidden field, out-of-range
    value, oversized delta, non-normalized weight set, or non-paper-only policy
    makes ok False.
    """
    violations: list[str] = []

    if policy.get("mode") != "paper_only":
        violations.append(f"paper_only_required: growth_policy.mode={policy.get('mode')!r}")

    module = str(mutation.get("module") or "")
    field = str(mutation.get("field") or "")

    forbidden = set(policy.get("forbidden_mutations") or [])
    if field in forbidden or module in forbidden:
        violations.append(f"forbidden_mutation: {field or module}")
        return False, violations  # never inspect a forbidden mutation further

    spec = ((policy.get("allowed_mutations") or {}).get(module) or {}).get(field)
    if spec is None:
        violations.append(f"field_not_in_whitelist: {module}.{field}")
        return False, violations

    if field == "component_weights":
        violations.extend(_validate_weights(mutation, spec))
        return (not violations), violations

    violations.extend(_validate_scalar(module, field, mutation, spec))
    return (not violations), violations


def _validate_scalar(module: str, field: str, mutation: dict[str, Any], spec: dict[str, Any]) -> list[str]:
    out: list[str] = []
    try:
        proposed = float(mutation["proposed"])
    except (KeyError, TypeError, ValueError):
        return [f"{module}.{field}: missing/invalid 'proposed'"]
    lo, hi = float(spec["min"]), float(spec["max"])
    if not (lo - _EPS <= proposed <= hi + _EPS):
        out.append(f"{module}.{field} proposed {proposed} outside [{lo}, {hi}]")
    if "current" in mutation and "max_delta" in spec:
        delta = abs(proposed - float(mutation["current"]))
        if delta > float(spec["max_delta"]) + _EPS:
            out.append(f"{module}.{field} delta {delta:g} > max_delta {spec['max_delta']}")
    return out


def _validate_weights(mutation: dict[str, Any], spec: dict[str, Any]) -> list[str]:
    out: list[str] = []
    proposed = mutation.get("proposed_weights") or {}
    if not proposed:
        return ["component_weights: missing 'proposed_weights'"]
    total = sum(float(v) for v in proposed.values())
    lo = float(spec.get("total_weight_min", 0.95))
    hi = float(spec.get("total_weight_max", 1.05))
    if not (lo - _EPS <= total <= hi + _EPS):
        out.append(f"component_weights total {total:.3f} outside [{lo}, {hi}]")
    max_delta = float(spec.get("max_delta_per_component", 1.0))
    current = mutation.get("current_weights") or {}
    for name, value in proposed.items():
        delta = abs(float(value) - float(current.get(name, value)))
        if delta > max_delta + _EPS:
            out.append(f"component_weight {name} delta {delta:.3f} > {max_delta}")
    return out
