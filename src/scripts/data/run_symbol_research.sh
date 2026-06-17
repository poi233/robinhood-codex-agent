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
run_date="$(pt_date)"
manual_root="$AGENT_ROOT/runtime/state/runs/$run_date/manual/$symbol"
manual_dir="$manual_root/market_feed"
manual_output="$manual_root/technical_signals.json"
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
  --date "$run_date" \
  --timeframes "$MARKET_FEED_TIMEFRAMES" \
  --news-limit "$MARKET_FEED_NEWS_LIMIT"

# Write the single-symbol analysis into manual/<SYMBOL>/ (next to its market_feed input), NOT the
# global signals/technical_signals.json. This stops an ad hoc one-symbol run from clobbering the
# day's full-watchlist technical file, and makes the output easy to find.
mkdir -p "$manual_root"
TECHNICAL_SIGNALS_PATH="$manual_output" MARKET_FEED_DIR="$manual_dir" \
  run_codex_prompt "technical_research" "$SRC_ROOT/prompts/technical/research.txt"

log_line "symbol_research wrote $manual_output"
printf 'Symbol research output: %s\n' "$manual_output"
