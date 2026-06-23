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
manual_features="$manual_root/technical_features.json"
manual_progress="$manual_root/technical_research.jsonl"
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

# Build the precomputed features AND the deterministic engine signals. The engine
# output is the decision-critical technical_signals.json; the narrative prompt below
# only enriches chan/Brooks/fundamentals on top of it.
mkdir -p "$manual_root"
rm -f "$manual_output"
"$resolved_python" - "$manual_dir" "$manual_features" "$manual_output" "$symbol" "$run_date" <<'PY'
import json
import sys
from pathlib import Path

from trading_agent.planner.technical_features import build_technical_features
from trading_agent.signals.technical_engine import build_technical_signals

market_feed_dir = Path(sys.argv[1])
features_path = Path(sys.argv[2])
signals_path = Path(sys.argv[3])
symbol = sys.argv[4]
run_date = sys.argv[5]
features_path.parent.mkdir(parents=True, exist_ok=True)
features = build_technical_features(market_feed_dir, [symbol], run_date)
features_path.write_text(json.dumps(features, indent=2, sort_keys=True) + "\n", encoding="utf-8")
signals = build_technical_signals(
    features, run_date=run_date, source_feed_manifest=str(market_feed_dir / "manifest.json")
)
signals_path.write_text(json.dumps(signals, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

# Write the single-symbol analysis into manual/<SYMBOL>/ (next to its market_feed input), NOT the
# global signals/technical_signals.json. This stops an ad hoc one-symbol run from clobbering the
# day's full-watchlist technical file, and makes the output easy to find. The narrative pass is
# advisory: if disabled, the deterministic engine output above already stands.
if [[ "${ENABLE_TECHNICAL_NARRATIVE:-1}" == "1" ]]; then
  TECHNICAL_SIGNALS_PATH="$manual_output" TECHNICAL_FEATURES_PATH="$manual_features" \
    PROGRESS_LOG_PATH="$manual_progress" MARKET_FEED_DIR="$manual_dir" \
    run_codex_prompt "technical_research" "$SRC_ROOT/prompts/technical/research.txt" || \
    log_line "symbol_research narrative enrichment failed; engine signals retained"
  # Fold the prompt's bounded llm_assessment into the decision (no-op if absent).
  "$resolved_python" -c "from trading_agent.signals.technical_engine import reconcile_technical_signals_file as r; r('$manual_output')" || \
    log_line "symbol_research llm reconciliation failed; engine signals retained"
fi

if [[ ! -s "$manual_output" ]]; then
  log_line "symbol_research failed: missing expected output $manual_output"
  exit 1
fi

log_line "symbol_research wrote $manual_output"
printf 'Symbol research output: %s\n' "$manual_output"
