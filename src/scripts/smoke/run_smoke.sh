#!/usr/bin/env bash

# Integration smoke test (L2). Runs the read-only / local command surface end-to-end and prints a
# PASS/FAIL summary, so "is the whole thing still wired up?" is one command. Best-effort: every step
# runs even if an earlier one fails; the script exits non-zero iff any *required* step failed.
#
# Network-dependent steps (yfinance: analytics calibrate / ai-signal-study / ai-ablation) and
# Codex/MCP lifecycle steps (premarket/intraday/postmarket) are OPTIONAL here — they are marked and
# do not fail the smoke unless you opt in:
#   SMOKE_INCLUDE_NETWORK=1    also run the yfinance-backed analytics
#   SMOKE_INCLUDE_LIFECYCLE=1  also dry-run premarket/intraday/postmarket (needs Codex/MCP)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=src/scripts/lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"
cd "$AGENT_ROOT"
python_bin="$(resolve_runtime_python_bin)" || { echo "no Python 3.11+ interpreter found"; exit 1; }

pass=0; fail=0; optfail=0
results=()

smoke() {     # smoke "label" <command...>  — required step
  local label="$1"; shift
  if "$@" >/dev/null 2>&1; then results+=("PASS      $label"); pass=$((pass + 1))
  else local c=$?; results+=("FAIL      $label (exit $c)"); fail=$((fail + 1)); fi
}
smoke_opt() { # optional step — failure recorded but does not fail the smoke
  local label="$1"; shift
  if "$@" >/dev/null 2>&1; then results+=("PASS      $label"); pass=$((pass + 1))
  else local c=$?; results+=("FAIL(opt) $label (exit $c)"); optfail=$((optfail + 1)); fi
}

echo "Running smoke (AGENT_ROOT=$AGENT_ROOT) ..."

# 1) Config + safety
smoke "doctor"                 "$python_bin" -m trading_agent doctor
[[ -x ./src/scripts/safety/check_safety.sh ]] && smoke "safety check" ./src/scripts/safety/check_safety.sh

# 2) Local, read-only analytics (no network)
smoke "analytics build"        "$python_bin" -m trading_agent analytics build
smoke "analytics fill-quality" "$python_bin" -m trading_agent analytics fill-quality
smoke "analytics weight-suggestion" "$python_bin" -m trading_agent analytics weight-suggestion
smoke "analytics snapshot"     "$python_bin" -m trading_agent analytics snapshot
smoke "analytics trend"        "$python_bin" -m trading_agent analytics trend
smoke "analytics nightly-health" "$python_bin" -m trading_agent analytics nightly-health
smoke "replay"                 "$python_bin" -m trading_agent replay

# 3) Self-growth (paper/shadow only; writes files, enables nothing)
smoke "growth observe"         "$python_bin" -m trading_agent growth observe
smoke "growth propose"         "$python_bin" -m trading_agent growth propose
smoke "growth shadow"          "$python_bin" -m trading_agent growth shadow
smoke "growth evaluate"        "$python_bin" -m trading_agent growth evaluate

# 4) Network-backed analytics (yfinance) — opt in
if [[ "${SMOKE_INCLUDE_NETWORK:-0}" == "1" ]]; then
  smoke_opt "analytics calibrate"      "$python_bin" -m trading_agent analytics calibrate
  smoke_opt "analytics ai-signal-study" "$python_bin" -m trading_agent analytics ai-signal-study
  smoke_opt "analytics ai-ablation"    "$python_bin" -m trading_agent analytics ai-ablation
fi

# 5) Lifecycle dry-runs (Codex/MCP) — opt in
if [[ "${SMOKE_INCLUDE_LIFECYCLE:-0}" == "1" ]]; then
  smoke_opt "premarket (dry-run)"  env CODEX_EXEC_DRY_RUN=1 ./src/scripts/entrypoints/run_premarket.sh
  smoke_opt "intraday (outside-market)" env ALLOW_OUTSIDE_MARKET_TEST=1 ./src/scripts/entrypoints/run_intraday.sh
  smoke_opt "postmarket"           ./src/scripts/entrypoints/run_postmarket.sh
fi

echo ""
echo "=== smoke summary: $pass passed, $fail failed (+$optfail optional-failed) ==="
for r in "${results[@]}"; do echo "  $r"; done

[[ "$fail" -eq 0 ]]
