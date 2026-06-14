#!/usr/bin/env bash

set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 SYMBOL" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=src/scripts/lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

symbol="$(printf '%s' "$1" | tr '[:lower:]' '[:upper:]')"
manual_dir="$AGENT_ROOT/runtime/state/runs/$(pt_date)/manual/$symbol/market_feed"
universe_file="$(mktemp "${TMPDIR:-/tmp}/symbol-universe.XXXXXX")"
trap 'rm -f "$universe_file"' EXIT
printf '%s\n' "$symbol" > "$universe_file"

resolved_python="$(resolve_market_feed_python_bin)" || {
  log_line "symbol_research failed: no Python interpreter with yfinance found"
  printf '%s no Python interpreter with yfinance found for symbol research\n' "$(pt_now)" >> "$ERROR_LOG"
  exit 1
}

"$resolved_python" "$SRC_ROOT/scripts/data/collect_market_feed.py" \
  --universe-file "$universe_file" \
  --output-dir "$manual_dir" \
  --date "$(pt_date)" \
  --timeframes "$MARKET_FEED_TIMEFRAMES" \
  --news-limit "$MARKET_FEED_NEWS_LIMIT"

MARKET_FEED_DIR="$manual_dir" run_codex_prompt "technical_research" "$SRC_ROOT/prompts/technical/research.txt"
