#!/usr/bin/env bash

# Nightly read-only / shadow-only analysis batch (I1). Refreshes every analytics + self-growth
# artifact after the close so the dashboard and trend snapshots stay current. SAFETY: this batch is
# read-history + write-new-analysis + shadow-only — it never places orders, never changes
# TRADING_MODE / RISK_TIER / KILL_SWITCH, never writes the champion paper ledger, never edits the
# registry, and never approves or promotes. "Auto-run the improvement commands" != "auto-change the
# strategy". Each step is best-effort: a failure is logged and the batch continues.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=src/scripts/lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"
cd "$AGENT_ROOT"

if [[ "${ENABLE_NIGHTLY_ANALYSIS:-1}" != "1" ]]; then
  log_line "nightly analysis disabled (ENABLE_NIGHTLY_ANALYSIS=0); skipping"
  exit 0
fi

python_bin="$(resolve_runtime_python_bin)" || {
  log_line "nightly analysis failed: no Python 3.11+ interpreter found"
  printf '%s no Python 3.11+ interpreter found for nightly analysis\n' "$(pt_now)" >> "$ERROR_LOG"
  exit 1
}

NIGHTLY_LOG_DIR="${RUN_LOG_DIR}/nightly"
mkdir -p "$NIGHTLY_LOG_DIR"
ANALYSIS_LOG="${NIGHTLY_LOG_DIR}/analysis.log"
# Per-step pass/fail (one JSON line per step) so `analytics nightly-health` can surface failures (L4).
STEP_RESULTS="${NIGHTLY_LOG_DIR}/step_results.jsonl"
: > "$STEP_RESULTS"

run_step() {
  # run_step "label" <command...> — best-effort: logs start/end + exit code, never aborts the batch.
  local label="$1"; shift
  printf '%s [nightly] START %s\n' "$(pt_now)" "$label" >> "$ANALYSIS_LOG"
  if "$@" >> "$ANALYSIS_LOG" 2>&1; then
    printf '%s [nightly] OK    %s\n' "$(pt_now)" "$label" >> "$ANALYSIS_LOG"
    printf '{"step":"%s","status":"ok","exit_code":0,"timestamp":"%s"}\n' "$label" "$(pt_now)" >> "$STEP_RESULTS"
  else
    local code=$?
    printf '%s [nightly] FAIL  %s (exit %s)\n' "$(pt_now)" "$label" "$code" >> "$ANALYSIS_LOG"
    printf '%s nightly step failed: %s (exit %s)\n' "$(pt_now)" "$label" "$code" >> "$ERROR_LOG"
    printf '{"step":"%s","status":"fail","exit_code":%s,"timestamp":"%s"}\n' "$label" "$code" "$(pt_now)" >> "$STEP_RESULTS"
  fi
}

log_line "nightly analysis starting (date=$RUN_DATE_PT, log=$ANALYSIS_LOG)"

# 1) Rebuild the analytics DB + refresh the read-only calibration / fill / AI study reports.
run_step "analytics build"          "$python_bin" -m trading_agent analytics build
run_step "analytics calibrate"      "$python_bin" -m trading_agent analytics calibrate
run_step "analytics fill-quality"   "$python_bin" -m trading_agent analytics fill-quality
run_step "analytics ai-signal-study" "$python_bin" -m trading_agent analytics ai-signal-study
run_step "analytics ai-ablation"    "$python_bin" -m trading_agent analytics ai-ablation
run_step "analytics weight-suggestion" "$python_bin" -m trading_agent analytics weight-suggestion

# 2) Self-growth: observe -> propose (writes files only) -> validate -> shadow (approved-only) ->
#    evaluate (recommend-only). None of these enable, approve, or promote anything.
run_step "growth observe"           "$python_bin" -m trading_agent growth observe
run_step "growth propose"           "$python_bin" -m trading_agent growth propose
PROPOSALS_DIR="runtime/strategy_proposals/${RUN_DATE_PT}"
if [[ -d "$PROPOSALS_DIR" ]]; then
  run_step "growth validate"        "$python_bin" -m trading_agent growth validate "$PROPOSALS_DIR"
fi
run_step "growth shadow"            "$python_bin" -m trading_agent growth shadow
run_step "growth evaluate"          "$python_bin" -m trading_agent growth evaluate

# 3) Archive a dated snapshot of tonight's reports + refresh the trend series.
run_step "analytics snapshot"       "$python_bin" -m trading_agent analytics snapshot
run_step "analytics trend"          "$python_bin" -m trading_agent analytics trend

# 4) Health summary (report freshness + this run's failed steps) — surfaces silent best-effort failures.
run_step "analytics nightly-health" "$python_bin" -m trading_agent analytics nightly-health

log_line "nightly analysis finished (date=$RUN_DATE_PT)"
exit 0
