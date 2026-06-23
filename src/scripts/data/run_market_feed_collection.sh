#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=src/scripts/lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

acquire_lock "market_feed"

collector_args=(
  --universe-file "$SRC_ROOT/config/universe.txt"
  --output-dir "$MARKET_FEED_DIR"
  --date "$(pt_date)"
  --timeframes "$MARKET_FEED_TIMEFRAMES"
  --news-limit "$MARKET_FEED_NEWS_LIMIT"
)

if [[ "${CODEX_EXEC_DRY_RUN:-0}" == "1" ]]; then
  collector_args+=(--mock)
  resolved_python="$(resolve_runtime_python_bin)" || {
    log_line "market_feed failed: no Python 3.11+ interpreter found"
    printf '%s no Python 3.11+ interpreter found for market feed dry-run\n' "$(pt_now)" >> "$ERROR_LOG"
    exit 1
  }
else
  resolved_python="$(resolve_market_feed_python_bin)" || {
    log_line "market_feed failed: no Python 3.11+ interpreter with yfinance found"
    printf '%s no Python 3.11+ interpreter with yfinance found for market feed collection\n' "$(pt_now)" >> "$ERROR_LOG"
    exit 1
  }
fi

"$resolved_python" "$SRC_ROOT/scripts/data/collect_market_feed.py" \
  "${collector_args[@]}"
