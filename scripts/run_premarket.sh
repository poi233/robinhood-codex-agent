#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/common.sh
source "$SCRIPT_DIR/common.sh"

acquire_lock "premarket"

if ! is_weekday_pt && [[ "${ALLOW_WEEKEND_RUN:-0}" != "1" ]]; then
  log_line "premarket weekend skip."
  exit 0
fi

if [[ "${ENABLE_DSA_SIGNAL_LAYER:-1}" == "1" ]]; then
  if ! run_codex_prompt "dsa_premarket_scan" "$AGENT_ROOT/prompts/dsa_premarket_scan.txt"; then
    log_line "dsa_premarket_scan failed; continuing with main premarket research."
  fi
fi

if [[ "${ENABLE_KRONOS_SIGNAL_LAYER:-1}" == "1" ]]; then
  if ! "$SCRIPT_DIR/run_kronos_premarket_scan.sh"; then
    log_line "kronos_premarket_scan failed; continuing with main premarket research."
  fi
fi

if [[ "${ENABLE_MARKET_FEED_LAYER:-1}" == "1" ]]; then
  if ! "$SCRIPT_DIR/run_market_feed_collection.sh"; then
    log_line "market_feed_collection failed; continuing with main premarket research."
  fi
fi

if [[ "${ENABLE_TECHNICAL_SIGNAL_LAYER:-1}" == "1" ]]; then
  if ! "$SCRIPT_DIR/run_technical_research.sh"; then
    log_line "technical_research failed; continuing with main premarket research."
  fi
fi

run_codex_prompt "premarket" "$AGENT_ROOT/prompts/premarket_research.txt"
