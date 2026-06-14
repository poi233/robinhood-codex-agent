#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"
cd "$AGENT_ROOT"

args=()
if [[ "$#" -gt 0 ]]; then
  args=("$@")
fi
if [[ "${CODEX_EXEC_DRY_RUN:-0}" == "1" ]]; then
  args+=(--dry-run)
fi

if [[ "${#args[@]}" -gt 0 ]]; then
  python3 -m trading_agent postmarket "${args[@]}"
else
  python3 -m trading_agent postmarket
fi
