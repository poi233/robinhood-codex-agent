#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/common.sh
source "$SCRIPT_DIR/common.sh"

acquire_lock "technical_research"

if [[ "${ENABLE_TECHNICAL_SIGNAL_LAYER:-1}" != "1" ]]; then
  log_line "technical_research disabled; skipping."
  exit 0
fi

if [[ ! -f "$MARKET_FEED_DIR/manifest.json" ]]; then
  log_line "technical_research missing market-feed manifest: $MARKET_FEED_DIR/manifest.json"
  exit 1
fi

run_codex_prompt "technical_research" "$AGENT_ROOT/prompts/technical_research.txt"
