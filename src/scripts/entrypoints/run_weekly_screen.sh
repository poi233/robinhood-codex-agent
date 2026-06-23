#!/usr/bin/env bash

# Weekly Serenity-skill stock screener (O1). Discovers pool-external upstream bottleneck stocks
# (Codex + the serenity-supply-chain skill), factor-validates them, and — only when
# Weekly screener — auto-updates the universe ADD-ONLY (never deletes) + re-ranks, capped
# and rate-limited. SAFETY: selection layer only. It never trades, never changes TRADING_MODE /
# RISK_TIER / KILL_SWITCH, never places orders, and never touches sizing/risk. Runs on Sunday
# (a weekend day) on purpose, so do NOT add a weekday guard.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=src/scripts/lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"
cd "$AGENT_ROOT"

python_bin="$(resolve_runtime_python_bin)" || {
  log_line "weekly screen failed: no Python 3.11+ interpreter found"
  printf '%s no Python 3.11+ interpreter found for weekly screen\n' "$(pt_now)" >> "$ERROR_LOG"
  exit 1
}

log_line "weekly screener starting (date=$RUN_DATE_PT)"
"$python_bin" -m trading_agent screen "$@"
log_line "weekly screener finished (date=$RUN_DATE_PT)"
exit 0
