# Self-Growth Platform — Phase 1 Implementation Plan (G-pre + G0–G2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the read-only foundation of the self-growth platform — an extensibility seam (resolve strategy profiles by name without global env), a safety policy + validator, and an Observe→Diagnose diagnostics layer that writes `growth_observations.json` and surfaces it in the dashboard — with **zero change to any trading decision**.

**Architecture:** A new `src/trading_agent/growth/` package. `growth/policy.py` loads `src/config/growth_policy.json` (the safety boundary). `growth/validator.py` rejects any mutation that touches a forbidden field or exceeds a whitelisted range/delta (fail-closed). `growth/observations.py` builds a `GrowthContext` once (reusing `replay.build_replay_report` + `analytics`), runs global checks plus a registry of per-module `diagnosers/`, and writes `runtime/analytics/growth_observations.json`. The dashboard gains a read-only "Self-Growth Lab" section. A small backward-compatible refactor (`G-pre`) lets `load_scoring_profile`/`load_policy_profile` resolve a profile by explicit name — the seam that later unblocks shadow-running challengers (G6) without mutating `os.environ`.

**Tech Stack:** Python 3.11, stdlib only (`json`, `sqlite3`, `dataclasses`, `pathlib`), `pytest` (`pythonpath=src` via `pytest.ini`). Optional `streamlit` for the dashboard page (already an optional dependency). **No new runtime dependencies.**

**Scope note:** This plan is **Phase 1** of the G-phase in [`../../roadmap.md`](../../roadmap.md). It covers the extensibility seam (G-pre, profile resolution only) + G0 (safety policy + validator skeleton) + G1 (global observations) + G2 (module diagnosers + dashboard). Everything here is **read-only and paper-safe**: it never changes scoring/policy behavior, never touches review/live, never writes a trading parameter. G3–G8 (proposals, experiment queue, shadow runner, evaluator, promotion) are outlined at the end and are **not** implemented here.

**Safety invariants (must hold after every task):**
- No code in `growth/` ever writes to `src/config/*` (except tests writing to `tmp_path`), `strategy_registry.yaml`, `runtime.env*`, or any paper/decision/order ledger.
- `growth/` never imports or calls `apply_paper_intent`, `place_equity_order`, or any execution path.
- The full existing suite (`python3 -m pytest`) stays green at every commit.

---

## File Structure

**New files:**
- `src/config/growth_policy.json` — safety boundary: allowed/forbidden mutations, ranges, promotion rules.
- `src/trading_agent/growth/__init__.py` — empty package marker.
- `src/trading_agent/growth/policy.py` — `load_growth_policy(agent_root)` (forbidden list can only widen).
- `src/trading_agent/growth/validator.py` — `validate_mutation(mutation, policy) -> (ok, violations)`.
- `src/trading_agent/growth/observations.py` — `Observation`, `GrowthContext`, global checks, `build_growth_observations`, `write_growth_observations`.
- `src/trading_agent/growth/diagnosers/__init__.py` — `DIAGNOSERS` registry + `run_all(ctx)`.
- `src/trading_agent/growth/diagnosers/scoring.py` — scoring-module diagnoser.
- `src/trading_agent/growth/diagnosers/setups.py` — setup/entry diagnoser.
- `tests/trading_agent/growth/test_profiles_by_name.py`
- `tests/trading_agent/growth/test_growth_policy.py`
- `tests/trading_agent/growth/test_validator.py`
- `tests/trading_agent/growth/test_observations.py`
- `tests/trading_agent/growth/test_diagnosers.py`

**Modified files:**
- `src/trading_agent/planner/scoring_profiles.py` — `load_scoring_profile(config_dir, *, profile_name=None)`.
- `src/trading_agent/policy/profiles.py` — `load_policy_profile(agent_root, *, profile_name=None)`.
- `src/trading_agent/policy/loaders.py` — `load_policy_inputs(..., policy_profile_name=None)`.
- `src/trading_agent/cli.py` — `growth observe` subcommand.
- `src/trading_agent/dashboard/queries.py` — `growth_observations(agent_root)`.
- `src/trading_agent/dashboard/charts.py` — `growth_observations_view(payload)`.
- `src/trading_agent/dashboard/app.py` — Self-Growth Lab section.
- `docs/project-status.md` — maturity-table pointer.

---

## Task 1: G-pre — resolve scoring/policy profiles by name (extensibility seam)

**Why first:** This is the named extensibility bottleneck for the whole platform. Today `load_scoring_profile`/`load_policy_profile` read `os.environ["SCORING_PROFILE"]`/`["POLICY_PROFILE"]`, so running a challenger with a different profile requires mutating global env — unsafe for Champion+Challenger in one process (G6). Adding an optional `profile_name` param is small, **backward-compatible (default `None` = current env behavior)**, and independently testable. (The isolated-ledger half of G-pre — `build_experiment_paths` — has no consumer until G6 and is deferred there.)

**Files:**
- Modify: `src/trading_agent/planner/scoring_profiles.py:60-67`
- Modify: `src/trading_agent/policy/profiles.py:13-14`
- Modify: `src/trading_agent/policy/loaders.py:297-328`
- Test: `tests/trading_agent/growth/test_profiles_by_name.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/trading_agent/growth/test_profiles_by_name.py
from pathlib import Path

from trading_agent.planner.scoring_profiles import load_scoring_profile
from trading_agent.policy.profiles import load_policy_profile


def _write_scoring_yaml(config_dir: Path) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "scoring_profiles.yaml").write_text(
        "default_profile: aggressive_growth\n"
        "profiles:\n"
        "  aggressive_growth:\n"
        "    trade_threshold: 50\n"
        "  conservative:\n"
        "    trade_threshold: 70\n",
        encoding="utf-8",
    )


def test_scoring_profile_by_name_ignores_env(tmp_path, monkeypatch):
    _write_scoring_yaml(tmp_path / "config")
    monkeypatch.setenv("SCORING_PROFILE", "aggressive_growth")
    profile = load_scoring_profile(tmp_path / "config", profile_name="conservative")
    assert profile["name"] == "conservative"
    assert profile["trade_threshold"] == 70.0


def test_scoring_profile_default_still_reads_env(tmp_path, monkeypatch):
    _write_scoring_yaml(tmp_path / "config")
    monkeypatch.setenv("SCORING_PROFILE", "conservative")
    profile = load_scoring_profile(tmp_path / "config")
    assert profile["name"] == "conservative"


def test_policy_profile_by_name_ignores_env(tmp_path, monkeypatch):
    config_dir = tmp_path / "src" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "policy_profiles.json").write_text(
        '{"profiles": {"conservative": {"min_reward_risk": 1.75},'
        ' "aggressive_growth": {"min_reward_risk": 1.5}}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("POLICY_PROFILE", "aggressive_growth")
    profile = load_policy_profile(tmp_path, profile_name="conservative")
    assert profile["name"] == "conservative"
    assert profile["min_reward_risk"] == 1.75
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/trading_agent/growth/test_profiles_by_name.py -v`
Expected: FAIL — `load_scoring_profile() got an unexpected keyword argument 'profile_name'`.

- [ ] **Step 3: Implement the keyword-only param in `scoring_profiles.py`**

Change the signature and the one resolution line (everything else unchanged):

```python
def load_scoring_profile(config_dir: Path, *, profile_name: str | None = None) -> dict[str, Any]:
    path = config_dir / "scoring_profiles.yaml"
    if not path.exists():
        return dict(DEFAULT_SCORING_PROFILE)
    payload = _parse_scoring_profiles_yaml(path)
    profiles = payload.get("profiles") or {}
    default_name = str(payload.get("default_profile") or DEFAULT_SCORING_PROFILE["name"])
    requested_name = str(profile_name or os.environ.get("SCORING_PROFILE") or default_name)
```

- [ ] **Step 4: Implement the keyword-only param in `policy/profiles.py`**

```python
def load_policy_profile(agent_root: Path, *, profile_name: str | None = None) -> dict[str, Any]:
    resolved_name = profile_name or os.environ.get("POLICY_PROFILE", DEFAULT_POLICY_PROFILE)
    path = agent_root / "src" / "config" / "policy_profiles.json"
    if not path.exists():
        return {"name": resolved_name, "enabled": False}
    payload = read_json(path)
    profiles = payload.get("profiles") if isinstance(payload, dict) else None
    if not isinstance(profiles, dict):
        return {"name": resolved_name, "enabled": False}
    selected = profiles.get(resolved_name) or {}
    if not isinstance(selected, dict):
        selected = {}
    return {"name": resolved_name, **selected}
```

- [ ] **Step 5: Thread `policy_profile_name` through `load_policy_inputs`**

In `policy/loaders.py`, add the keyword to the signature (after `require_live_quotes: bool = False`):

```python
    require_live_quotes: bool = False,
    policy_profile_name: str | None = None,
) -> PolicyInputs:
```

and change the `policy_profile=` line inside the `PolicyInputs(...)` construction:

```python
        policy_profile=load_policy_profile(agent_root, profile_name=policy_profile_name),
```

- [ ] **Step 6: Run the new test + the existing profile/policy tests**

Run: `python3 -m pytest tests/trading_agent/growth/test_profiles_by_name.py tests/trading_agent/planner/test_scoring_profiles.py tests/trading_agent/policy -v`
Expected: PASS (new tests green; existing profile/policy tests unchanged and green).

- [ ] **Step 7: Commit**

```bash
git add src/trading_agent/planner/scoring_profiles.py src/trading_agent/policy/profiles.py \
        src/trading_agent/policy/loaders.py tests/trading_agent/growth/test_profiles_by_name.py
git commit -m "feat(growth): resolve scoring/policy profiles by explicit name (G-pre seam)"
```

---

## Task 2: G0 — growth_policy.json + loader

**Why JSON not YAML:** the docx wrote `growth_policy.yaml`, but this config is 4 levels deep. The codebase deliberately avoids `pyyaml` and hand-rolls minimal ≤2-level YAML parsers (`registry.py`, `scoring_profiles.py`). Deeply-nested config in this repo is JSON (`policy_profiles.json`, `risk_tiers.json`, `dsa_strategy_weights.json`). Using `growth_policy.json` is consistent, robust, and dependency-free.

**Files:**
- Create: `src/config/growth_policy.json`
- Create: `src/trading_agent/growth/__init__.py`
- Create: `src/trading_agent/growth/policy.py`
- Test: `tests/trading_agent/growth/test_growth_policy.py`

- [ ] **Step 1: Create the config file**

```json
{
  "enabled": true,
  "mode": "paper_only",
  "proposal": {
    "max_new_proposals_per_week": 2,
    "min_days_between_proposals": 5,
    "require_human_approval": true
  },
  "allowed_mutations": {
    "scoring": {
      "trade_threshold": {"min": 30, "max": 80, "max_delta": 10},
      "watchlist_threshold": {"min": 20, "max": 70, "max_delta": 10},
      "component_weights": {"max_delta_per_component": 0.10, "total_weight_min": 0.95, "total_weight_max": 1.05}
    },
    "policy": {
      "price_setup_weight": {"min": 0.05, "max": 0.35, "max_delta": 0.10},
      "min_reward_risk": {"min": 1.2, "max": 2.5, "max_delta": 0.25}
    },
    "setups": {
      "enabled_setups": {"allowed": ["pullback", "breakout", "trend_continuation"]}
    }
  },
  "forbidden_mutations": [
    "TRADING_MODE", "RISK_TIER", "PAPER_RISK_TIER", "KILL_SWITCH",
    "MCP_APPROVAL", "place_equity_order", "per_trade_risk_pct",
    "max_daily_risk_pct", "max_single_stock_weight"
  ],
  "promotion_rules": {
    "min_shadow_days": 10,
    "min_trading_days": 8,
    "fill_rate_not_worse_than_champion": true,
    "max_drawdown_not_worse_than_champion": true,
    "require_human_final_approval": true
  }
}
```

- [ ] **Step 2: Create the empty package marker**

```python
# src/trading_agent/growth/__init__.py
```

(Empty file, like `analytics/__init__.py`.)

- [ ] **Step 3: Write the failing test**

```python
# tests/trading_agent/growth/test_growth_policy.py
import json
from pathlib import Path

from trading_agent.growth.policy import DEFAULT_GROWTH_POLICY, load_growth_policy


def test_load_growth_policy_reads_repo_config():
    policy = load_growth_policy(Path.cwd())
    assert policy["mode"] == "paper_only"
    assert "TRADING_MODE" in policy["forbidden_mutations"]
    assert policy["allowed_mutations"]["scoring"]["trade_threshold"]["max_delta"] == 10


def test_missing_file_falls_back_to_safe_defaults(tmp_path):
    policy = load_growth_policy(tmp_path)
    assert policy["enabled"] is False
    assert "place_equity_order" in policy["forbidden_mutations"]


def test_forbidden_list_can_only_widen(tmp_path):
    config_dir = tmp_path / "src" / "config"
    config_dir.mkdir(parents=True)
    # A tampered config that tries to DROP the forbidden list entirely.
    (config_dir / "growth_policy.json").write_text(
        json.dumps({"mode": "paper_only", "forbidden_mutations": ["foo"]}),
        encoding="utf-8",
    )
    policy = load_growth_policy(tmp_path)
    # Hard defaults are always unioned back in; "foo" is added, KILL_SWITCH not removed.
    assert "KILL_SWITCH" in policy["forbidden_mutations"]
    assert "foo" in policy["forbidden_mutations"]
```

- [ ] **Step 4: Run test to verify it fails**

Run: `python3 -m pytest tests/trading_agent/growth/test_growth_policy.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trading_agent.growth.policy'`.

- [ ] **Step 5: Implement `growth/policy.py`**

```python
# src/trading_agent/growth/policy.py
from __future__ import annotations

from pathlib import Path
from typing import Any

from trading_agent.core.io import read_json

# Hard safety defaults. The forbidden list here can never be narrowed by config;
# load_growth_policy always unions these back in.
DEFAULT_GROWTH_POLICY: dict[str, Any] = {
    "enabled": False,
    "mode": "paper_only",
    "proposal": {
        "max_new_proposals_per_week": 2,
        "min_days_between_proposals": 5,
        "require_human_approval": True,
    },
    "allowed_mutations": {},
    "forbidden_mutations": [
        "TRADING_MODE", "RISK_TIER", "PAPER_RISK_TIER", "KILL_SWITCH",
        "MCP_APPROVAL", "place_equity_order", "per_trade_risk_pct",
        "max_daily_risk_pct", "max_single_stock_weight",
    ],
    "promotion_rules": {},
}


def load_growth_policy(agent_root: Path) -> dict[str, Any]:
    """Load src/config/growth_policy.json merged over safe defaults.

    The forbidden_mutations list is treated as union-only: whatever the file
    says, the hard defaults are always added back, so a tampered or partial
    config can widen the deny-list but never weaken it.
    """
    path = agent_root / "src" / "config" / "growth_policy.json"
    if not path.exists():
        return _with_forbidden_defaults(dict(DEFAULT_GROWTH_POLICY))
    payload = read_json(path)
    if not isinstance(payload, dict):
        return _with_forbidden_defaults(dict(DEFAULT_GROWTH_POLICY))
    merged = {**DEFAULT_GROWTH_POLICY, **payload}
    return _with_forbidden_defaults(merged, payload.get("forbidden_mutations"))


def _with_forbidden_defaults(policy: dict[str, Any], extra: Any = None) -> dict[str, Any]:
    forbidden = set(DEFAULT_GROWTH_POLICY["forbidden_mutations"])
    if isinstance(extra, list):
        forbidden.update(str(item) for item in extra)
    else:
        forbidden.update(policy.get("forbidden_mutations") or [])
    policy["forbidden_mutations"] = sorted(forbidden)
    return policy
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python3 -m pytest tests/trading_agent/growth/test_growth_policy.py -v`
Expected: PASS (3 tests).

- [ ] **Step 7: Commit**

```bash
git add src/config/growth_policy.json src/trading_agent/growth/__init__.py \
        src/trading_agent/growth/policy.py tests/trading_agent/growth/test_growth_policy.py
git commit -m "feat(growth): add growth_policy.json safety boundary + loader (G0)"
```

---

## Task 3: G0 — mutation validator (fail-closed)

**Files:**
- Create: `src/trading_agent/growth/validator.py`
- Test: `tests/trading_agent/growth/test_validator.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/trading_agent/growth/test_validator.py
from pathlib import Path

from trading_agent.growth.policy import load_growth_policy
from trading_agent.growth.validator import validate_mutation

POLICY = load_growth_policy(Path.cwd())


def test_forbidden_field_is_rejected():
    ok, violations = validate_mutation(
        {"module": "risk", "field": "per_trade_risk_pct", "current": 0.005, "proposed": 0.02}, POLICY
    )
    assert ok is False
    assert any("forbidden_mutation" in v for v in violations)


def test_out_of_range_is_rejected():
    ok, violations = validate_mutation(
        {"module": "scoring", "field": "trade_threshold", "current": 50, "proposed": 95}, POLICY
    )
    assert ok is False
    assert any("outside" in v for v in violations)


def test_over_delta_is_rejected():
    ok, violations = validate_mutation(
        {"module": "scoring", "field": "trade_threshold", "current": 50, "proposed": 70}, POLICY
    )
    assert ok is False
    assert any("delta" in v for v in violations)


def test_valid_paper_only_mutation_passes():
    ok, violations = validate_mutation(
        {"module": "scoring", "field": "trade_threshold", "current": 50, "proposed": 56}, POLICY
    )
    assert ok is True
    assert violations == []


def test_field_not_in_whitelist_is_rejected():
    ok, violations = validate_mutation(
        {"module": "scoring", "field": "mystery_knob", "current": 1, "proposed": 2}, POLICY
    )
    assert ok is False
    assert any("not_in_whitelist" in v for v in violations)


def test_component_weights_sum_must_stay_normalized():
    ok, violations = validate_mutation(
        {
            "module": "scoring",
            "field": "component_weights",
            "current_weights": {"dsa": 0.25, "technical": 0.30, "kronos": 0.15, "quote": 0.10, "catalyst": 0.20},
            "proposed_weights": {"dsa": 0.50, "technical": 0.30, "kronos": 0.15, "quote": 0.10, "catalyst": 0.20},
        },
        POLICY,
    )
    assert ok is False  # sum 1.25 outside [0.95, 1.05] AND dsa delta 0.25 > 0.10


def test_non_paper_only_policy_is_rejected():
    ok, violations = validate_mutation(
        {"module": "scoring", "field": "trade_threshold", "current": 50, "proposed": 56},
        {**POLICY, "mode": "live"},
    )
    assert ok is False
    assert any("paper_only" in v for v in violations)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/trading_agent/growth/test_validator.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trading_agent.growth.validator'`.

- [ ] **Step 3: Implement `growth/validator.py`**

```python
# src/trading_agent/growth/validator.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/trading_agent/growth/test_validator.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add src/trading_agent/growth/validator.py tests/trading_agent/growth/test_validator.py
git commit -m "feat(growth): add fail-closed mutation validator (G0)"
```

---

## Task 4: G1 — global observations + `growth_observations.json`

**Files:**
- Create: `src/trading_agent/growth/observations.py`
- Test: `tests/trading_agent/growth/test_observations.py`

Detects from the existing replay report + manifests: `low_trade_frequency`, `high_no_trade_rate`, `dominant_blocked_reason`, `high_pending_cancel_rate`, `missing_manifest`. (`analyzer_failure_rate` is module-specific and lands in Task 6's analyzers diagnoser.)

- [ ] **Step 1: Write the failing test**

```python
# tests/trading_agent/growth/test_observations.py
import json
from pathlib import Path

from trading_agent.growth.observations import (
    build_growth_observations,
    default_growth_observations_path,
    write_growth_observations,
)


def _seed_run(agent_root: Path, run_date: str, *, decisions: list[dict], orders: list[dict], manifest: bool) -> None:
    run_dir = agent_root / "runtime" / "state" / "runs" / run_date
    audit = run_dir / "logs"  # not used; decisions/orders resolved via build_runtime_paths
    paper = run_dir / "paper"
    paper.mkdir(parents=True, exist_ok=True)
    # decisions.jsonl lives under runtime/logs/runs/<date>/audit/ per RuntimePaths
    dec_dir = agent_root / "runtime" / "logs" / "runs" / run_date / "audit"
    dec_dir.mkdir(parents=True, exist_ok=True)
    with (dec_dir / "decisions.jsonl").open("w", encoding="utf-8") as fh:
        for row in decisions:
            fh.write(json.dumps(row) + "\n")
    with (paper / "orders.jsonl").open("w", encoding="utf-8") as fh:
        for row in orders:
            fh.write(json.dumps(row) + "\n")
    if manifest:
        (run_dir / "run_manifest.json").write_text(json.dumps({"strategy_id": "baseline_v1"}), encoding="utf-8")


def test_high_no_trade_rate_and_missing_manifest(tmp_path):
    # 5 no-trade decisions, all blocked by outside_entry_zone; no manifest.
    decisions = [
        {"timestamp": f"2026-06-15T07:0{i}:00-0700", "decision": "no_action",
         "blocked_reasons": ["outside_entry_zone"]}
        for i in range(5)
    ]
    _seed_run(tmp_path, "2026-06-15", decisions=decisions, orders=[], manifest=False)

    payload = build_growth_observations(tmp_path)
    types = {o["type"] for o in payload["global"]}
    assert "high_no_trade_rate" in types
    assert "dominant_blocked_reason" in types
    assert "missing_manifest" in types
    # modules key exists (filled in G2); empty/absent diagnosers are fine here.
    assert "modules" in payload


def test_write_growth_observations_is_read_only_artifact(tmp_path):
    _seed_run(tmp_path, "2026-06-15", decisions=[{"decision": "would_trade", "blocked_reasons": []}],
              orders=[], manifest=True)
    out = write_growth_observations(tmp_path)
    assert out == default_growth_observations_path(tmp_path)
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert "generated_at" in data and "global" in data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/trading_agent/growth/test_observations.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trading_agent.growth.observations'`.

- [ ] **Step 3: Implement `growth/observations.py`**

```python
# src/trading_agent/growth/observations.py
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import write_json
from trading_agent.replay.analysis import build_replay_report, discover_run_dates

# Thresholds. Kept module-level (not in growth_policy.json) because they tune the
# *diagnostics*, not any trading parameter; promoting them to config is a later option.
LOW_TRADE_FREQUENCY_PER_DAY = 0.25
HIGH_NO_TRADE_RATE_PCT = 80.0
DOMINANT_BLOCKED_REASON_PCT = 50.0
HIGH_PENDING_CANCEL_RATE_PCT = 50.0


@dataclass
class Observation:
    type: str
    module: str
    severity: str  # "info" | "warning" | "critical"
    evidence: dict[str, Any]
    suggested_action: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GrowthContext:
    agent_root: Path
    run_dates: list[str]
    replay: dict[str, Any]


def build_growth_context(agent_root: Path, *, since: str | None = None, until: str | None = None) -> GrowthContext:
    """Compute the shared, relatively expensive inputs once for all diagnosers."""
    run_dates = discover_run_dates(agent_root, since_date=since, until_date=until)
    replay = build_replay_report(agent_root, since_date=since, until_date=until)
    return GrowthContext(agent_root=agent_root, run_dates=run_dates, replay=replay)


def global_observations(ctx: GrowthContext) -> list[Observation]:
    obs: list[Observation] = []
    fr = ctx.replay.get("fill_rate") or {}
    br = ctx.replay.get("blocked_reasons") or {}
    n_days = max(len(ctx.run_dates), 1)

    filled = int(fr.get("filled") or 0)
    per_day = filled / n_days
    if ctx.run_dates and per_day < LOW_TRADE_FREQUENCY_PER_DAY:
        obs.append(Observation(
            "low_trade_frequency", "global", "warning",
            {"filled": filled, "run_days": n_days, "fills_per_day": round(per_day, 3)},
            "System rarely fills; review entry thresholds / watchlist breadth (paper experiment).",
        ))

    no_trade_rate = float(br.get("no_trade_rate_pct") or 0.0)
    if int(br.get("total_evaluations") or 0) > 0 and no_trade_rate >= HIGH_NO_TRADE_RATE_PCT:
        obs.append(Observation(
            "high_no_trade_rate", "global", "warning",
            {"no_trade_rate_pct": no_trade_rate, "total_evaluations": br.get("total_evaluations")},
            "Most evaluations end in no-trade; inspect dominant blocked reason.",
        ))

    reason_counts = br.get("reason_counts") or {}
    total_reasons = sum(int(v) for v in reason_counts.values())
    if total_reasons > 0:
        top_reason, top_count = max(reason_counts.items(), key=lambda kv: int(kv[1]))
        pct = top_count / total_reasons * 100
        if pct >= DOMINANT_BLOCKED_REASON_PCT:
            obs.append(Observation(
                "dominant_blocked_reason", "global", "info",
                {"reason": top_reason, "count": int(top_count), "pct": round(pct, 1)},
                f"{round(pct, 1)}% of no-trades are {top_reason!r}; target that gate for tuning.",
            ))

    canceled = int(fr.get("canceled") or 0)
    total_orders = int(fr.get("total_orders") or 0)
    if total_orders > 0:
        cancel_rate = canceled / total_orders * 100
        if cancel_rate >= HIGH_PENDING_CANCEL_RATE_PCT:
            obs.append(Observation(
                "high_pending_cancel_rate", "paper", "warning",
                {"canceled": canceled, "total_orders": total_orders, "cancel_rate_pct": round(cancel_rate, 1)},
                "Many limits never fill before day-end cancel; review entry-zone / chase tolerance.",
            ))

    missing = [
        d for d in ctx.run_dates
        if not (build_runtime_paths(ctx.agent_root, run_date=d).run_state_dir / "run_manifest.json").exists()
    ]
    if missing:
        obs.append(Observation(
            "missing_manifest", "global", "warning",
            {"run_dates_without_manifest": missing, "count": len(missing)},
            "These runs are not traceable to a strategy version; ensure run_manifest is written.",
        ))
    return obs


def build_growth_observations(agent_root: Path, *, since: str | None = None, until: str | None = None) -> dict[str, Any]:
    ctx = build_growth_context(agent_root, since=since, until=until)
    # Lazy import avoids a package import cycle (diagnosers import this module).
    from trading_agent.growth.diagnosers import run_all

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_date_range": {"since": since, "until": until},
        "run_date_count": len(ctx.run_dates),
        "global": [o.to_dict() for o in global_observations(ctx)],
        "modules": run_all(ctx),
    }


def default_growth_observations_path(agent_root: Path) -> Path:
    return agent_root / "runtime" / "analytics" / "growth_observations.json"


def write_growth_observations(agent_root: Path, *, since: str | None = None, until: str | None = None) -> Path:
    payload = build_growth_observations(agent_root, since=since, until=until)
    path = default_growth_observations_path(agent_root)
    write_json(path, payload)
    return path
```

Note: `build_growth_observations` calls `run_all` from the diagnosers package (Task 6). Until Task 6 lands, create a temporary shim so this task's tests pass on their own:

- [ ] **Step 4: Create a minimal diagnosers package shim (replaced in Task 6)**

```python
# src/trading_agent/growth/diagnosers/__init__.py
from __future__ import annotations

from typing import Any

from trading_agent.growth.observations import GrowthContext


def run_all(ctx: GrowthContext) -> dict[str, list[dict[str, Any]]]:
    """Placeholder; real per-module diagnosers are registered in Task 6."""
    return {}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/trading_agent/growth/test_observations.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add src/trading_agent/growth/observations.py src/trading_agent/growth/diagnosers/__init__.py \
        tests/trading_agent/growth/test_observations.py
git commit -m "feat(growth): global growth observations + growth_observations.json (G1)"
```

---

## Task 5: G1 — `growth observe` CLI subcommand

**Files:**
- Modify: `src/trading_agent/cli.py:9-32` (parser) and `src/trading_agent/cli.py:151-180` (dispatch)
- Test: `tests/trading_agent/test_cli.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/trading_agent/test_cli.py
def test_growth_observe_writes_artifact(tmp_path, monkeypatch, capsys):
    import json
    from trading_agent.cli import main

    run_dir = tmp_path / "runtime" / "state" / "runs" / "2026-06-15"
    run_dir.mkdir(parents=True)
    (run_dir / "run_manifest.json").write_text(json.dumps({"strategy_id": "baseline_v1"}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    rc = main(["growth", "observe"])
    assert rc == 0
    out = tmp_path / "runtime" / "analytics" / "growth_observations.json"
    assert out.exists()
    assert "growth_observations.json" in capsys.readouterr().out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/trading_agent/test_cli.py::test_growth_observe_writes_artifact -v`
Expected: FAIL — `argument command: invalid choice: 'growth'`.

- [ ] **Step 3: Add the subparser**

In `build_parser()`, before `return parser`:

```python
    growth_parser = subparsers.add_parser("growth", help="Self-growth diagnostics (paper-only, read-only).")
    growth_subparsers = growth_parser.add_subparsers(dest="growth_command", required=True)
    growth_observe_parser = growth_subparsers.add_parser("observe", help="Write runtime/analytics/growth_observations.json.")
    growth_observe_parser.add_argument("--since", metavar="YYYY-MM-DD", default=None)
    growth_observe_parser.add_argument("--until", metavar="YYYY-MM-DD", default=None)
```

- [ ] **Step 4: Add the dispatch + handler**

Add a handler near `_run_analytics_build`:

```python
def _run_growth_observe(agent_root: Path, *, since: str | None, until: str | None) -> int:
    from trading_agent.growth.observations import write_growth_observations

    path = write_growth_observations(agent_root, since=since, until=until)
    print(f"Wrote {path}")
    return 0
```

And in `main()`, before `return 0`:

```python
    if args.command == "growth" and args.growth_command == "observe":
        return _run_growth_observe(Path.cwd(), since=args.since, until=args.until)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/trading_agent/test_cli.py -v`
Expected: PASS (new test green; existing CLI tests unchanged).

- [ ] **Step 6: Commit**

```bash
git add src/trading_agent/cli.py tests/trading_agent/test_cli.py
git commit -m "feat(growth): add 'growth observe' CLI subcommand (G1)"
```

---

## Task 6: G2 — diagnoser registry + module diagnosers

Replaces the Task-4 shim with a real, extensible registry. Adds two representative diagnosers (`scoring`, `setups`); the registry makes adding `analyzers`/`risk`/`watchlist`/`features`/`paper`/`prompt` a matter of dropping in a module and registering it — no change to existing diagnosers (open/closed).

**Files:**
- Modify: `src/trading_agent/growth/diagnosers/__init__.py`
- Create: `src/trading_agent/growth/diagnosers/scoring.py`
- Create: `src/trading_agent/growth/diagnosers/setups.py`
- Test: `tests/trading_agent/growth/test_diagnosers.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/trading_agent/growth/test_diagnosers.py
import json
from pathlib import Path

from trading_agent.growth.diagnosers import DIAGNOSERS, run_all
from trading_agent.growth.observations import GrowthContext


def test_registry_exposes_named_diagnosers():
    assert "scoring" in DIAGNOSERS
    assert "setups" in DIAGNOSERS


def test_setups_diagnoser_flags_dominant_setup_gates():
    ctx = GrowthContext(
        agent_root=Path("/nonexistent"),
        run_dates=["2026-06-15"],
        replay={"blocked_reasons": {"reason_counts": {"outside_entry_zone": 6, "missing_quote": 1}}},
    )
    result = run_all(ctx)
    setup_obs = result["setups"]
    assert any(o["type"] == "setup_gates_dominate_no_trades" for o in setup_obs)


def test_scoring_diagnoser_flags_recurring_theme_concentration(tmp_path):
    run_dir = tmp_path / "runtime" / "state" / "runs" / "2026-06-15" / "planner"
    run_dir.mkdir(parents=True)
    (run_dir / "premarket_diagnostics.json").write_text(
        json.dumps({"warnings": ["theme_concentration_exceeded:tradable:ai_semiconductor:70%>50%"]}),
        encoding="utf-8",
    )
    ctx = GrowthContext(agent_root=tmp_path, run_dates=["2026-06-15"], replay={})
    result = run_all(ctx)
    assert any(o["type"] == "recurring_theme_concentration" for o in result["scoring"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/trading_agent/growth/test_diagnosers.py -v`
Expected: FAIL — `ImportError: cannot import name 'DIAGNOSERS'`.

- [ ] **Step 3: Implement the setups diagnoser**

```python
# src/trading_agent/growth/diagnosers/setups.py
from __future__ import annotations

from trading_agent.growth.observations import GrowthContext, Observation

SETUP_RELATED_REASONS = ("outside_entry_zone", "chase_blocked", "reward_risk_too_low", "no_trade_zone")
DOMINANCE_PCT = 40.0


def diagnose(ctx: GrowthContext) -> list[Observation]:
    counts = ((ctx.replay.get("blocked_reasons") or {}).get("reason_counts") or {})
    total = sum(int(v) for v in counts.values())
    if total == 0:
        return []
    setup_block = sum(int(counts.get(r, 0)) for r in SETUP_RELATED_REASONS)
    pct = setup_block / total * 100
    if pct < DOMINANCE_PCT:
        return []
    return [
        Observation(
            "setup_gates_dominate_no_trades", "setups", "info",
            {
                "setup_block": setup_block,
                "total_blocks": total,
                "pct": round(pct, 1),
                "reasons": {r: int(counts.get(r, 0)) for r in SETUP_RELATED_REASONS if counts.get(r)},
            },
            "Entry/RR gates drive most no-trades; consider price_setup_weight / entry-tolerance experiments (paper).",
        )
    ]
```

- [ ] **Step 4: Implement the scoring diagnoser**

```python
# src/trading_agent/growth/diagnosers/scoring.py
from __future__ import annotations

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import read_json
from trading_agent.growth.observations import GrowthContext, Observation


def diagnose(ctx: GrowthContext) -> list[Observation]:
    flagged: list[str] = []
    for run_date in ctx.run_dates:
        path = build_runtime_paths(ctx.agent_root, run_date=run_date).premarket_diagnostics_path
        if not path.exists():
            continue
        payload = read_json(path)
        if not isinstance(payload, dict):
            continue
        warnings = payload.get("warnings") or []
        if any(
            str(w).startswith(("theme_concentration_exceeded", "speculative_concentration_exceeded"))
            for w in warnings
        ):
            flagged.append(run_date)
    if not flagged:
        return []
    return [
        Observation(
            "recurring_theme_concentration", "scoring", "info",
            {"run_dates": flagged, "count": len(flagged)},
            "Theme/speculative caps repeatedly exceeded; consider a watchlist-cap experiment (paper).",
        )
    ]
```

- [ ] **Step 5: Implement the registry**

```python
# src/trading_agent/growth/diagnosers/__init__.py
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
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python3 -m pytest tests/trading_agent/growth/test_diagnosers.py tests/trading_agent/growth/test_observations.py -v`
Expected: PASS (diagnoser tests green; observations tests still green now that `modules` is populated).

- [ ] **Step 7: Commit**

```bash
git add src/trading_agent/growth/diagnosers/ tests/trading_agent/growth/test_diagnosers.py
git commit -m "feat(growth): module diagnoser registry + scoring/setups diagnosers (G2)"
```

---

## Task 7: G2 — dashboard "Self-Growth Lab" read-only page

**Files:**
- Modify: `src/trading_agent/dashboard/queries.py` (append)
- Modify: `src/trading_agent/dashboard/charts.py` (append)
- Modify: `src/trading_agent/dashboard/app.py` (append section)
- Test: `tests/trading_agent/dashboard/test_queries.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/trading_agent/dashboard/test_queries.py
def test_growth_observations_missing_returns_empty(tmp_path):
    from trading_agent.dashboard.queries import growth_observations

    assert growth_observations(tmp_path) == {}


def test_growth_observations_reads_artifact(tmp_path):
    import json
    from trading_agent.dashboard.queries import growth_observations

    out = tmp_path / "runtime" / "analytics"
    out.mkdir(parents=True)
    (out / "growth_observations.json").write_text(
        json.dumps({"global": [{"type": "high_no_trade_rate"}], "modules": {}}), encoding="utf-8"
    )
    payload = growth_observations(tmp_path)
    assert payload["global"][0]["type"] == "high_no_trade_rate"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/trading_agent/dashboard/test_queries.py -v`
Expected: FAIL — `ImportError: cannot import name 'growth_observations'`.

- [ ] **Step 3: Add the query helper**

Append to `dashboard/queries.py`:

```python
def growth_observations(agent_root: Path) -> dict[str, Any]:
    """Read-only: runtime/analytics/growth_observations.json (empty if not built yet)."""
    from trading_agent.growth.observations import default_growth_observations_path

    return _read_json_or_empty(default_growth_observations_path(agent_root))
```

- [ ] **Step 4: Add the chart view**

Append to `dashboard/charts.py` (match the existing thin-wrapper style):

```python
def growth_observations_view(payload: dict) -> None:
    import streamlit as st

    if not payload:
        st.info("No growth observations yet. Run: python3 -m trading_agent growth observe")
        return
    st.caption(f"generated_at: {payload.get('generated_at', '?')}  ·  run dates: {payload.get('run_date_count', 0)}")
    glob = payload.get("global") or []
    if glob:
        st.subheader("Global")
        st.dataframe(glob, use_container_width=True)
    modules = payload.get("modules") or {}
    flat = [{"module": m, **o} for m, obs in modules.items() for o in obs]
    if flat:
        st.subheader("By module")
        st.dataframe(flat, use_container_width=True)
    if not glob and not flat:
        st.success("No issues detected.")
```

- [ ] **Step 5: Add the app section**

Append to `dashboard/app.py`:

```python
st.header("Self-Growth Lab (read-only diagnostics)")
charts.growth_observations_view(queries.growth_observations(AGENT_ROOT))
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python3 -m pytest tests/trading_agent/dashboard/test_queries.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/trading_agent/dashboard/queries.py src/trading_agent/dashboard/charts.py \
        src/trading_agent/dashboard/app.py tests/trading_agent/dashboard/test_queries.py
git commit -m "feat(growth): read-only Self-Growth Lab dashboard section (G2)"
```

---

## Task 8: Docs + full-suite verification

**Files:**
- Modify: `docs/project-status.md`
- Test: full suite

- [ ] **Step 1: Update the maturity table in `docs/project-status.md`**

Under `## 一、整体成熟度`, add a row (after the dashboard row):

```markdown
| 自成长诊断（growth observe / Self-Growth Lab） | ✅ G0–G2 已加（只读，见 roadmap G） |
```

- [ ] **Step 2: Run the full suite**

Run: `python3 -m pytest`
Expected: PASS — all pre-existing tests plus the new `tests/trading_agent/growth/*` and appended CLI/dashboard tests. Report the exact passed count.

- [ ] **Step 3: Manually exercise the CLI (smoke)**

Run: `python3 -m trading_agent growth observe`
Expected: prints `Wrote .../runtime/analytics/growth_observations.json`; file is valid JSON with `global`/`modules` keys.

- [ ] **Step 4: Commit**

```bash
git add docs/project-status.md
git commit -m "docs: record G0-G2 self-growth diagnostics in project status"
```

---

## Self-Review (run against the spec)

**1. Spec coverage (docx §12 G0–G2 + extensibility):**
- G0 safety boundary (`growth_policy` + forbidden_mutations + paper_only) → Tasks 2–3. ✅
- G0 validator skeleton rejecting forbidden/out-of-range/over-delta → Task 3. ✅
- G1 observations (`low_trade_frequency`, `high_no_trade_rate`, `dominant_blocked_reason`, `high_pending_cancel_rate`, `missing_manifest`) + `growth_observations.json` + `growth observe` CLI → Tasks 4–5. ✅ (`analyzer_failure_rate` deferred to a Task-6-style analyzers diagnoser; noted.)
- G2 module diagnosers with `type/module/severity/evidence/suggested_action` + dashboard Self-Growth Lab → Tasks 6–7. ✅
- Extensibility seam (profile-by-name) → Task 1. ✅
- "Do not change trading decisions / behavior / review-live" → safety invariants + every module is read-only. ✅

**2. Placeholder scan:** every code step shows complete code; every command shows expected output. The Task-4 `diagnosers/__init__.py` shim is explicitly a temporary stub replaced in Task 6 (not a placeholder — it's runnable and tested). ✅

**3. Type consistency:** `Observation`/`GrowthContext` defined in `observations.py` (Task 4) and imported unchanged by diagnosers (Task 6) and the registry. `validate_mutation(mutation, policy) -> tuple[bool, list[str]]` consistent across Task 3 and its tests. `load_growth_policy(agent_root)`, `build_growth_observations(agent_root, *, since, until)`, `write_growth_observations(...) -> Path`, `default_growth_observations_path(agent_root)` referenced consistently in Tasks 4/5/7. `run_all(ctx) -> dict[str, list[dict]]` consistent between the shim (Task 4) and the real registry (Task 6). ✅

---

## Subsequent Phases (NOT in this plan)

These build on Phase 1 and are sequenced in [`../../roadmap.md`](../../roadmap.md) (G phase). Each needs its own plan when started.

- **G-pre (remainder): isolated experiment ledgers.** Add `build_experiment_paths(agent_root, run_date, strategy_id)` rooting `paper_*`/`decisions`/`orders` under `runtime/state/runs/<date>/experiments/<strategy_id>/`. **Deferred to G6** because it has no consumer until the shadow runner (YAGNI).
- **G3 Proposal generator** (`growth/proposals.py`): observations → `runtime/strategy_proposals/<date>/proposal_*.yaml|md`; whitelist fields only; never auto-enable.
- **G4 Proposal validator (full)**: reuse `validate_mutation`; write `*_validation.json`; mark `rejected`/`validated`.
- **G5 Experiment queue** (`src/config/strategy_experiments.yaml` + `growth/experiment_queue.py`): `proposed→human_approved→active_shadow→ready_for_review→promoted/rejected/archived`; CLI `growth experiments list/approve/archive`; approve only enables shadow, never switches `active_strategy`.
- **G6 Shadow runner** (`growth/shadow_runner.py`): uses Task-1's profile-by-name + isolated ledgers + the pure `generate_order_intent` to run challengers on the same inputs; champion ledger untouched. Cheapest for policy-only challengers (reuse premarket artifacts); scoring/watchlist challengers need a premarket re-score.
- **G7 Evaluator** (`growth/evaluator.py`): champion vs challengers on fill_rate / no_trade_rate / forward returns (reuse E1) / drawdown / safety violations → `experiment_report.json` + `promotion_recommendation.md`; recommend only.
- **G8 Human promotion**: `strategy promote check` validates + drafts changelog; switching `active_strategy` stays a manual YAML edit.
