#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=src/scripts/lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

if [[ "$TRADING_MODE" != "paper" ]]; then
  log_line "run_all_paper_once refused: TRADING_MODE=$TRADING_MODE"
  printf '%s run_all_paper_once requires TRADING_MODE=paper, got %s\n' "$(pt_now)" "$TRADING_MODE" >> "$ERROR_LOG"
  exit 1
fi

KILL_SWITCH_BACKUP="$AGENT_ROOT/runtime/state/paper_test_switch_backup"

restore_kill_switch() {
  if [[ -f "$KILL_SWITCH_BACKUP" ]]; then
    mv "$KILL_SWITCH_BACKUP" "$AGENT_ROOT/KILL_SWITCH"
    log_line "restored KILL_SWITCH after paper full-suite run"
  fi
}

trap restore_kill_switch EXIT

if [[ -f "$AGENT_ROOT/KILL_SWITCH" ]]; then
  mv "$AGENT_ROOT/KILL_SWITCH" "$KILL_SWITCH_BACKUP"
  log_line "temporarily disabled KILL_SWITCH for paper full-suite run"
fi

"$SCRIPT_DIR/run_premarket.sh"
"$SCRIPT_DIR/run_intraday.sh"
"$SCRIPT_DIR/run_postmarket.sh"
