#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

acquire_lock "dsa_premarket_scan"

if ! is_weekday_pt && [[ "${ALLOW_WEEKEND_RUN:-0}" != "1" ]]; then
  log_line "dsa_premarket_scan weekend skip."
  exit 0
fi

run_codex_prompt "dsa_premarket_scan" "$AGENT_ROOT/prompts/signals/dsa_scan.txt"
