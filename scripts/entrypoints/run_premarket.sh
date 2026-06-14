#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"
cd "$AGENT_ROOT"
python_bin="$(resolve_market_feed_python_bin)"

args=()
if [[ "$#" -gt 0 ]]; then
  args=("$@")
fi
if [[ "${CODEX_EXEC_DRY_RUN:-0}" == "1" ]]; then
  args+=(--dry-run)
fi

if [[ "${#args[@]}" -gt 0 ]]; then
  "$python_bin" -m trading_agent premarket "${args[@]}"
else
  "$python_bin" -m trading_agent premarket
fi
