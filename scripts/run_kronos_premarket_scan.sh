#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/common.sh
source "$SCRIPT_DIR/common.sh"

acquire_lock "kronos_premarket_scan"

if ! is_weekday_pt && [[ "${ALLOW_WEEKEND_RUN:-0}" != "1" ]]; then
  log_line "kronos_premarket_scan weekend skip."
  exit 0
fi

OUTPUT_FILE="$KRONOS_SIGNALS_PATH"
RUN_DATE="$RUN_DATE_PT"

cmd=(
  "$KRONOS_PYTHON_BIN"
  "$AGENT_ROOT/scripts/kronos_generate_signals.py"
  "--universe-file" "$AGENT_ROOT/config/universe.txt"
  "--output-file" "$OUTPUT_FILE"
  "--date" "$RUN_DATE"
)

if [[ "${KRONOS_USE_MOCK:-0}" == "1" ]]; then
  cmd+=("--mock")
fi

log_line "kronos_premarket_scan starting timeframe=$KRONOS_TIMEFRAME model=$KRONOS_MODEL_NAME"
"${cmd[@]}" >> "$RUN_LOG" 2>> "$ERROR_LOG"
log_line "kronos_premarket_scan completed output=$OUTPUT_FILE"
