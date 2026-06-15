#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=src/scripts/lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

acquire_lock "dsa_premarket_scan"

if ! is_weekday_pt && [[ "${ALLOW_WEEKEND_RUN:-0}" != "1" ]]; then
  log_line "dsa_premarket_scan weekend skip."
  exit 0
fi

PYTHON_BIN="$(resolve_runtime_python_bin || true)"
if [[ -z "$PYTHON_BIN" ]]; then
  printf '%s no Python 3.11+ interpreter found for dsa_premarket_scan\n' "$(pt_now)" >> "$ERROR_LOG"
  exit 1
fi

"$PYTHON_BIN" -m trading_agent dsa
