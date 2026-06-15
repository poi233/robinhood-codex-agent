#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=src/scripts/lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"
cd "$AGENT_ROOT"
python_bin="$(resolve_runtime_python_bin)" || {
  log_line "intraday failed: no Python 3.11+ interpreter found"
  printf '%s no Python 3.11+ interpreter found for intraday\n' "$(pt_now)" >> "$ERROR_LOG"
  exit 1
}

args=()
if [[ "$#" -gt 0 ]]; then
  args=("$@")
fi
if [[ "${CODEX_EXEC_DRY_RUN:-0}" == "1" ]]; then
  args+=(--dry-run)
fi

if [[ "${#args[@]}" -gt 0 ]]; then
  "$python_bin" -m trading_agent intraday "${args[@]}"
else
  "$python_bin" -m trading_agent intraday
fi
