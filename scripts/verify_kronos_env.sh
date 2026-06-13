#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/common.sh
source "$SCRIPT_DIR/common.sh"

[[ -x "$KRONOS_PYTHON_BIN" ]] || { echo "missing executable KRONOS_PYTHON_BIN: $KRONOS_PYTHON_BIN"; exit 1; }
[[ -d "$KRONOS_PROJECT_ROOT" ]] || { echo "missing KRONOS_PROJECT_ROOT: $KRONOS_PROJECT_ROOT"; exit 1; }

"$KRONOS_PYTHON_BIN" - <<PY
import sys
from pathlib import Path
sys.path.insert(0, r"$KRONOS_PROJECT_ROOT")
import pandas  # noqa: F401
import torch  # noqa: F401
import yfinance  # noqa: F401
from model import Kronos, KronosPredictor, KronosTokenizer  # noqa: F401
print("python imports ok")
PY

"$KRONOS_PYTHON_BIN" "$AGENT_ROOT/scripts/kronos_generate_signals.py" \
  --universe-file "$AGENT_ROOT/config/universe.txt" \
  --output-file "$AGENT_ROOT/state/kronos_signals.json" \
  --date "$(pt_date)" \
  --mock

echo "Kronos portable verification passed."
