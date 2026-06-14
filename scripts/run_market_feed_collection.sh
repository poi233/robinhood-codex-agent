#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/common.sh
source "$SCRIPT_DIR/common.sh"

acquire_lock "market_feed"

if [[ "${ENABLE_MARKET_FEED_LAYER:-1}" != "1" ]]; then
  log_line "market_feed disabled; skipping."
  exit 0
fi

collector_args=(
  --universe-file "$AGENT_ROOT/config/universe.txt"
  --output-dir "$MARKET_FEED_DIR"
  --date "$(pt_date)"
  --timeframes "$MARKET_FEED_TIMEFRAMES"
  --news-limit "$MARKET_FEED_NEWS_LIMIT"
)

if [[ "${CODEX_EXEC_DRY_RUN:-0}" == "1" ]]; then
  collector_args+=(--mock)
fi

resolved_python="$(resolve_market_feed_python_bin)" || {
  log_line "market_feed failed: no Python interpreter with yfinance found"
  printf '%s no Python interpreter with yfinance found for market feed collection\n' "$(pt_now)" >> "$ERROR_LOG"
  exit 1
}

"$resolved_python" "$AGENT_ROOT/scripts/collect_market_feed.py" \
  "${collector_args[@]}"
