#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=src/scripts/lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

acquire_lock "technical_research"

if [[ "${ENABLE_TECHNICAL_SIGNAL_LAYER:-1}" != "1" ]]; then
  log_line "technical_research disabled; skipping."
  exit 0
fi

if [[ ! -f "$MARKET_FEED_DIR/manifest.json" ]]; then
  log_line "technical_research missing market-feed manifest: $MARKET_FEED_DIR/manifest.json"
  exit 1
fi

run_date="$(pt_date)"
python_bin="$(resolve_runtime_python_bin)" || {
  log_line "technical_research failed: no Python 3.11+ interpreter found"
  exit 1
}

# Decision-critical technical signals are computed deterministically in Python from
# the precomputed features. The narrative prompt below only enriches them.
"$python_bin" - "$MARKET_FEED_DIR" "$TECHNICAL_FEATURES_PATH" "$TECHNICAL_SIGNALS_PATH" "$SRC_ROOT/config" "$run_date" <<'PY'
import json
import sys
from pathlib import Path

from trading_agent.data.universe import parse_active_watchlist
from trading_agent.planner.technical_features import build_technical_features
from trading_agent.signals.technical_engine import build_technical_signals

market_feed_dir = Path(sys.argv[1])
features_path = Path(sys.argv[2])
signals_path = Path(sys.argv[3])
config_dir = Path(sys.argv[4])
run_date = sys.argv[5]

symbols = parse_active_watchlist(config_dir)

features = build_technical_features(market_feed_dir, symbols, run_date)
features_path.parent.mkdir(parents=True, exist_ok=True)
features_path.write_text(json.dumps(features, indent=2, sort_keys=True) + "\n", encoding="utf-8")
signals = build_technical_signals(
    features, run_date=run_date, source_feed_manifest=str(market_feed_dir / "manifest.json")
)
signals_path.parent.mkdir(parents=True, exist_ok=True)
signals_path.write_text(json.dumps(signals, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

if [[ "${ENABLE_TECHNICAL_NARRATIVE:-1}" == "1" ]]; then
  run_codex_prompt "technical_research" "$SRC_ROOT/prompts/technical/research.txt" || \
    log_line "technical_research narrative enrichment failed; deterministic engine signals retained"
fi
