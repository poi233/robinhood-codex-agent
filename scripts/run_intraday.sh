#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/common.sh
source "$SCRIPT_DIR/common.sh"

acquire_lock "intraday"

if ! is_weekday_pt && [[ "${ALLOW_WEEKEND_RUN:-0}" != "1" ]]; then
  log_line "intraday weekend skip."
  append_local_decision "intraday" "calendar_skip" "not_a_weekday_pt"
  exit 0
fi

if ! is_intraday_window_pt && [[ "${ALLOW_OUTSIDE_MARKET_TEST:-0}" != "1" ]]; then
  log_line "intraday outside configured PT window, skipping."
  append_local_decision "intraday" "time_window_skip" "outside_intraday_window_pt"
  exit 0
fi

if [[ "$(kill_switch_status)" == "present" && "${ALLOW_KILL_SWITCH_PAPER_TEST:-0}" != "1" ]]; then
  log_line "KILL_SWITCH exists, skipping intraday run."
  append_local_decision "intraday" "kill_switch_skip" "KILL_SWITCH_present"
  exit 0
fi

run_codex_prompt "intraday" "$AGENT_ROOT/prompts/intraday_check.txt"
