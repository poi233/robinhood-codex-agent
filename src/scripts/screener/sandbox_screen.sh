#!/usr/bin/env bash

# Sandbox tester for the O1 weekly screener's WRITE path. Copies src/config into a throwaway
# AGENT_ROOT so `screen --apply` (or a deterministic offline write demo) exercises the real
# universe.txt / universe_meta.json mutation logic WITHOUT touching your real config. The real
# src/config is verified unchanged at the end.
#
# Usage:
#   src/scripts/screener/sandbox_screen.sh                 # full live path: real `screen --apply`
#                                                          #   (uses Codex+yfinance if available)
#   src/scripts/screener/sandbox_screen.sh --offline-demo  # deterministic offline write demo
#                                                          #   (synthetic candidates; no network)
#
# Selection layer only — never trades. Safe to run repeatedly.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO_ROOT"

MODE="live"
if [[ "${1:-}" == "--offline-demo" ]]; then
  MODE="offline"
  shift
fi

SANDBOX="$(mktemp -d -t screener-sandbox-XXXXXX)"
mkdir -p "$SANDBOX/src"
cp -R src/config "$SANDBOX/src/config"
ln -s "$REPO_ROOT/src/trading_agent" "$SANDBOX/src/trading_agent"
ln -s "$REPO_ROOT/src/prompts" "$SANDBOX/src/prompts"

real_universe="src/config/universe.txt"
before_real="$(md5sum "$real_universe" | awk '{print $1}')"
before_count="$(grep -cvE '^\s*#|^\s*$' "$real_universe" || true)"

echo "sandbox AGENT_ROOT : $SANDBOX"
echo "real universe size : $before_count symbols (will be verified untouched)"
echo "mode               : $MODE"
echo

if [[ "$MODE" == "offline" ]]; then
  AGENT_ROOT="$SANDBOX" PYTHONPATH=src python3 - <<'PY'
import json, os
from pathlib import Path

from trading_agent.data.universe import parse_universe, parse_active_watchlist
from trading_agent.screener.factor_gate import CandidateEvaluation
from trading_agent.screener.paths import screener_run_dir
from trading_agent.screener.universe_update import (
    apply_universe_update, plan_universe_update, write_audit,
)

agent_root = Path(os.environ["AGENT_ROOT"])
cfg = agent_root / "src" / "config"
run_dir = screener_run_dir(agent_root)

existing = parse_universe(cfg / "universe.txt")
meta_raw = json.loads((cfg / "universe_meta.json").read_text()) if (cfg / "universe_meta.json").exists() else {}
meta = {k: v for k, v in meta_raw.items() if isinstance(v, dict)}
pins = {s.upper() for s in parse_active_watchlist(cfg)}


def ev(sym, score, passed=True, reason=None):
    return CandidateEvaluation(sym, score, passed, reason, "ok", 100.0, 5e7, 1.0, 1.0, 1.0, True, True)


# Two synthetic "discovered" names that pass the gate, plus descending scores for existing symbols
# so a cap-demotion is deterministic.
discovered = [
    {"symbol": "SBXA", "theme": "sandbox_demo", "thesis": "synthetic add A"},
    {"symbol": "SBXB", "theme": "sandbox_demo", "thesis": "synthetic add B"},
]
evals = {"SBXA": ev("SBXA", 99.0), "SBXB": ev("SBXB", 98.0)}
for i, s in enumerate(existing):
    evals.setdefault(s, ev(s, float(len(existing) - i)))  # earlier = higher score

plan = plan_universe_update(
    existing_symbols=existing,
    existing_meta=meta,
    evaluations=evals,
    discovered=discovered,
    max_adds_per_week=5,
    universe_max=len(existing),  # +2 adds → 2 demotions of the lowest-ranked non-protected watch
    protected=pins,
)
res = apply_universe_update(config_dir=cfg, run_dir=run_dir, run_date="SANDBOX", plan=plan)
write_audit(run_dir=run_dir, run_date="SANDBOX", plan=plan, applied=True)

print("added   :", res["added"])
print("demoted :", res["demoted"])
print("backup  :", res["backup_dir"])
print("audit   :", run_dir / "universe_change.md")
PY
else
  AGENT_ROOT="$SANDBOX" PYTHONPATH=src python3 -m trading_agent screen --apply "$@"
fi

echo
echo "=== sandbox universe.txt (tail) ==="
tail -n 8 "$SANDBOX/src/config/universe.txt"

echo
after_real="$(md5sum "$real_universe" | awk '{print $1}')"
if [[ "$before_real" == "$after_real" ]]; then
  echo "OK: real $real_universe is UNCHANGED (all writes went to the sandbox copy)"
else
  echo "ERROR: real $real_universe changed — this should never happen!" >&2
  exit 1
fi

echo
echo "Inspect the sandbox at: $SANDBOX"
echo "  universe diff : diff src/config/universe.txt $SANDBOX/src/config/universe.txt"
echo "  audit         : cat $SANDBOX/runtime/screener/*/universe_change.md"
echo "Clean up with   : rm -rf $SANDBOX"
