# Kronos Premarket Portable Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a portable Kronos premarket signal layer that can be rebuilt on a new machine from this repository, while keeping Kronos advisory-only and non-blocking inside the trading pipeline.

**Architecture:** Extend the existing shell-plus-state-file workflow with repository-owned setup and verification scripts. The repo will create `.venv-kronos`, clone a fixed Kronos commit into `.vendor/kronos`, write machine-local overrides into `config/runtime.env.local`, and run a Python generator that emits `state/runs/<date>/signals/kronos_signals.json` for the main premarket prompt to consume.

**Tech Stack:** Bash, Python 3.11, `unittest`, `venv`, upstream Kronos source checkout, `torch`, `pandas`, `yfinance`, Codex prompts, local JSON state files

---

## File Map

- Create: `config/runtime.env.local.example`
- Create: `requirements-kronos-extra.txt`
- Create: `docs/setup/kronos-portable-setup.md`
- Create: `scripts/kronos/setup_kronos_env.sh`
- Create: `scripts/kronos/verify_kronos_env.sh`
- Create: `scripts/kronos/kronos_generate_signals.py`
- Create: `scripts/kronos/run_kronos_premarket_scan.sh`
- Create: `tests/test_kronos_generate_signals.py`
- Modify: `.gitignore`
- Modify: `config/runtime.env`
- Modify: `README.md`
- Modify: `scripts/lib/common.sh`
- Modify: `scripts/safety/check_safety.sh`
- Modify: `scripts/entrypoints/run_premarket.sh`
- Modify: `prompts/premarket/final_research.txt`

### Responsibility Split

- `.gitignore`: ignore repo-local runtime artifacts and machine-local env overrides.
- `config/runtime.env`: committed defaults for all machines.
- `config/runtime.env.local.example`: local override template for machine paths.
- `requirements-kronos-extra.txt`: repo-specific Python additions on top of upstream Kronos requirements.
- `scripts/kronos/setup_kronos_env.sh`: clone Kronos at a fixed commit, create `.venv-kronos`, install dependencies, and generate `config/runtime.env.local`.
- `scripts/kronos/verify_kronos_env.sh`: verify that the portable environment is usable.
- `scripts/lib/common.sh`: layered env loading and defaults shared across shell scripts.
- `scripts/kronos/kronos_generate_signals.py`: universe parsing, mock/live signal generation, and JSON output.
- `scripts/kronos/run_kronos_premarket_scan.sh`: shell runner for the Kronos signal layer.
- `prompts/premarket/final_research.txt`: describe how the main premarket agent consumes Kronos safely.
- `scripts/safety/check_safety.sh`: report whether portable setup and wiring are complete.
- `README.md` and `docs/setup/kronos-portable-setup.md`: operator installation and rebuild instructions.
- `tests/test_kronos_generate_signals.py`: contract and runner regression tests without needing Robinhood or Codex auth.

## Implementation Notes

- Portable install locations are fixed:
  - `.vendor/kronos`
  - `.venv-kronos`
- Fixed upstream version:
  - repo: `https://github.com/shiyu-coder/Kronos.git`
  - commit: `67b630e67f6a18c9e9be918d9b4337c960db1e9a`
- Machine-local overrides live in `config/runtime.env.local` and must never be committed.
- Setup must fail fast; runtime must degrade safely.
- Mock mode must work before Codex login or Robinhood authentication is complete.

### Task 1: Add Repo-Local Config Layering and Ignore Rules

**Files:**
- Modify: `.gitignore`
- Modify: `config/runtime.env`
- Modify: `scripts/lib/common.sh`

- [ ] **Step 1: Add failing coverage for local env loading behavior**

Create `tests/test_kronos_generate_signals.py` with this first test block:

```python
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


class CommonRuntimeTests(unittest.TestCase):
    def test_common_sh_prefers_runtime_env_local(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            config_dir = tmp / "config"
            scripts_dir = tmp / "scripts"
            config_dir.mkdir()
            scripts_dir.mkdir()

            (config_dir / "runtime.env").write_text("TRADING_MODE=paper\n", encoding="utf-8")
            (config_dir / "runtime.env.local").write_text("TRADING_MODE=review\n", encoding="utf-8")
            (scripts_dir / "common.sh").write_text((REPO_ROOT / "scripts" / "common.sh").read_text(encoding="utf-8"), encoding="utf-8")

            result = subprocess.run(
                ["bash", "-lc", f"cd {tmp} && source scripts/lib/common.sh && printf '%s' \"$TRADING_MODE\""],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "review")
```

- [ ] **Step 2: Run the test and verify it fails because `scripts/lib/common.sh` does not read `runtime.env.local` yet**

Run: `python3 -m unittest tests/test_kronos_generate_signals.py -v`

Expected: FAIL in `test_common_sh_prefers_runtime_env_local` with `paper` or unset output instead of `review`.

- [ ] **Step 3: Update `.gitignore` for portable local artifacts**

Add these lines:

```gitignore
config/runtime.env.local
.vendor/
.venv-kronos/
```

- [ ] **Step 4: Add committed portable defaults to `config/runtime.env`**

Append these lines:

```bash
# Optional Kronos forecast layer.
ENABLE_KRONOS_SIGNAL_LAYER=1
KRONOS_MODEL_NAME=NeoQuasar/Kronos-small
KRONOS_TOKENIZER_NAME=NeoQuasar/Kronos-Tokenizer-base
KRONOS_TIMEFRAME=30m
KRONOS_LOOKBACK_BARS=400
KRONOS_HORIZON_BARS=8
KRONOS_TEMPERATURE=1.0
KRONOS_TOP_P=0.9
KRONOS_SAMPLE_COUNT=1
KRONOS_MIN_CONFIDENCE=0.60
```

- [ ] **Step 5: Modify `scripts/lib/common.sh` to load `runtime.env.local` after `runtime.env`**

Add these variables near the top:

```bash
CONFIG_ENV_LOCAL="$AGENT_ROOT/config/runtime.env.local"
```

Load both files:

```bash
if [[ -f "$CONFIG_ENV" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$CONFIG_ENV"
  set +a
fi

if [[ -f "$CONFIG_ENV_LOCAL" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$CONFIG_ENV_LOCAL"
  set +a
fi
```

Add overrides and defaults:

```bash
OVERRIDE_ENABLE_KRONOS_SIGNAL_LAYER="${ENABLE_KRONOS_SIGNAL_LAYER-}"
OVERRIDE_KRONOS_PYTHON_BIN="${KRONOS_PYTHON_BIN-}"
OVERRIDE_KRONOS_PROJECT_ROOT="${KRONOS_PROJECT_ROOT-}"
OVERRIDE_KRONOS_MODEL_NAME="${KRONOS_MODEL_NAME-}"
OVERRIDE_KRONOS_TOKENIZER_NAME="${KRONOS_TOKENIZER_NAME-}"
OVERRIDE_KRONOS_TIMEFRAME="${KRONOS_TIMEFRAME-}"
OVERRIDE_KRONOS_LOOKBACK_BARS="${KRONOS_LOOKBACK_BARS-}"
OVERRIDE_KRONOS_HORIZON_BARS="${KRONOS_HORIZON_BARS-}"
OVERRIDE_KRONOS_TEMPERATURE="${KRONOS_TEMPERATURE-}"
OVERRIDE_KRONOS_TOP_P="${KRONOS_TOP_P-}"
OVERRIDE_KRONOS_SAMPLE_COUNT="${KRONOS_SAMPLE_COUNT-}"
OVERRIDE_KRONOS_MIN_CONFIDENCE="${KRONOS_MIN_CONFIDENCE-}"
```

And:

```bash
[[ -n "$OVERRIDE_ENABLE_KRONOS_SIGNAL_LAYER" ]] && ENABLE_KRONOS_SIGNAL_LAYER="$OVERRIDE_ENABLE_KRONOS_SIGNAL_LAYER"
[[ -n "$OVERRIDE_KRONOS_PYTHON_BIN" ]] && KRONOS_PYTHON_BIN="$OVERRIDE_KRONOS_PYTHON_BIN"
[[ -n "$OVERRIDE_KRONOS_PROJECT_ROOT" ]] && KRONOS_PROJECT_ROOT="$OVERRIDE_KRONOS_PROJECT_ROOT"
[[ -n "$OVERRIDE_KRONOS_MODEL_NAME" ]] && KRONOS_MODEL_NAME="$OVERRIDE_KRONOS_MODEL_NAME"
[[ -n "$OVERRIDE_KRONOS_TOKENIZER_NAME" ]] && KRONOS_TOKENIZER_NAME="$OVERRIDE_KRONOS_TOKENIZER_NAME"
[[ -n "$OVERRIDE_KRONOS_TIMEFRAME" ]] && KRONOS_TIMEFRAME="$OVERRIDE_KRONOS_TIMEFRAME"
[[ -n "$OVERRIDE_KRONOS_LOOKBACK_BARS" ]] && KRONOS_LOOKBACK_BARS="$OVERRIDE_KRONOS_LOOKBACK_BARS"
[[ -n "$OVERRIDE_KRONOS_HORIZON_BARS" ]] && KRONOS_HORIZON_BARS="$OVERRIDE_KRONOS_HORIZON_BARS"
[[ -n "$OVERRIDE_KRONOS_TEMPERATURE" ]] && KRONOS_TEMPERATURE="$OVERRIDE_KRONOS_TEMPERATURE"
[[ -n "$OVERRIDE_KRONOS_TOP_P" ]] && KRONOS_TOP_P="$OVERRIDE_KRONOS_TOP_P"
[[ -n "$OVERRIDE_KRONOS_SAMPLE_COUNT" ]] && KRONOS_SAMPLE_COUNT="$OVERRIDE_KRONOS_SAMPLE_COUNT"
[[ -n "$OVERRIDE_KRONOS_MIN_CONFIDENCE" ]] && KRONOS_MIN_CONFIDENCE="$OVERRIDE_KRONOS_MIN_CONFIDENCE"

ENABLE_KRONOS_SIGNAL_LAYER="${ENABLE_KRONOS_SIGNAL_LAYER:-1}"
KRONOS_PYTHON_BIN="${KRONOS_PYTHON_BIN:-$AGENT_ROOT/.venv-kronos/bin/python}"
KRONOS_PROJECT_ROOT="${KRONOS_PROJECT_ROOT:-$AGENT_ROOT/.vendor/kronos}"
KRONOS_MODEL_NAME="${KRONOS_MODEL_NAME:-NeoQuasar/Kronos-small}"
KRONOS_TOKENIZER_NAME="${KRONOS_TOKENIZER_NAME:-NeoQuasar/Kronos-Tokenizer-base}"
KRONOS_TIMEFRAME="${KRONOS_TIMEFRAME:-30m}"
KRONOS_LOOKBACK_BARS="${KRONOS_LOOKBACK_BARS:-400}"
KRONOS_HORIZON_BARS="${KRONOS_HORIZON_BARS:-8}"
KRONOS_TEMPERATURE="${KRONOS_TEMPERATURE:-1.0}"
KRONOS_TOP_P="${KRONOS_TOP_P:-0.9}"
KRONOS_SAMPLE_COUNT="${KRONOS_SAMPLE_COUNT:-1}"
KRONOS_MIN_CONFIDENCE="${KRONOS_MIN_CONFIDENCE:-0.60}"
```

- [ ] **Step 6: Re-run the test and verify local overrides now win**

Run: `python3 -m unittest tests/test_kronos_generate_signals.py -v`

Expected: PASS for `test_common_sh_prefers_runtime_env_local`.

- [ ] **Step 7: Commit the config-layering changes**

```bash
git add .gitignore config/runtime.env scripts/lib/common.sh tests/test_kronos_generate_signals.py
git commit -m "feat: add portable runtime env layering"
```

### Task 2: Add Portable Setup and Verification Scripts

**Files:**
- Create: `config/runtime.env.local.example`
- Create: `requirements-kronos-extra.txt`
- Create: `scripts/kronos/setup_kronos_env.sh`
- Create: `scripts/kronos/verify_kronos_env.sh`
- Create: `docs/setup/kronos-portable-setup.md`

- [ ] **Step 1: Add failing tests for setup artifacts that should exist after bootstrap**

Extend `tests/test_kronos_generate_signals.py` with:

```python
class PortableArtifactTests(unittest.TestCase):
    def test_runtime_env_local_example_exists(self) -> None:
        self.assertTrue((REPO_ROOT / "config" / "runtime.env.local.example").exists())

    def test_requirements_kronos_extra_exists(self) -> None:
        self.assertTrue((REPO_ROOT / "requirements-kronos-extra.txt").exists())

    def test_setup_and_verify_scripts_exist(self) -> None:
        self.assertTrue((REPO_ROOT / "scripts" / "setup_kronos_env.sh").exists())
        self.assertTrue((REPO_ROOT / "scripts" / "verify_kronos_env.sh").exists())
```

- [ ] **Step 2: Run the tests and verify the new artifact checks fail**

Run: `python3 -m unittest tests/test_kronos_generate_signals.py -v`

Expected: FAIL for the new artifact existence tests.

- [ ] **Step 3: Create `config/runtime.env.local.example`**

Use exactly:

```bash
# Machine-local Kronos overrides.
KRONOS_PYTHON_BIN=/abs/path/to/repo/.venv-kronos/bin/python
KRONOS_PROJECT_ROOT=/abs/path/to/repo/.vendor/kronos
```

- [ ] **Step 4: Create `requirements-kronos-extra.txt`**

Use exactly:

```text
yfinance
```

- [ ] **Step 5: Create `scripts/kronos/setup_kronos_env.sh`**

Use this script body:

```bash
#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
KRONOS_REPO_URL="https://github.com/shiyu-coder/Kronos.git"
KRONOS_COMMIT_SHA="67b630e67f6a18c9e9be918d9b4337c960db1e9a"
VENV_DIR="$REPO_ROOT/.venv-kronos"
VENDOR_DIR="$REPO_ROOT/.vendor"
KRONOS_DIR="$VENDOR_DIR/kronos"
LOCAL_ENV_EXAMPLE="$REPO_ROOT/config/runtime.env.local.example"
LOCAL_ENV_FILE="$REPO_ROOT/config/runtime.env.local"

command -v git >/dev/null 2>&1 || { echo "missing git"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "missing python3"; exit 1; }

mkdir -p "$VENDOR_DIR"

if [[ ! -d "$VENV_DIR" ]]; then
  python3 -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install --upgrade pip

if [[ ! -d "$KRONOS_DIR/.git" ]]; then
  git clone "$KRONOS_REPO_URL" "$KRONOS_DIR"
fi

git -C "$KRONOS_DIR" fetch --all --tags
git -C "$KRONOS_DIR" checkout "$KRONOS_COMMIT_SHA"

"$VENV_DIR/bin/pip" install -r "$KRONOS_DIR/requirements.txt"
"$VENV_DIR/bin/pip" install -r "$REPO_ROOT/requirements-kronos-extra.txt"

if [[ ! -f "$LOCAL_ENV_FILE" ]]; then
  cp "$LOCAL_ENV_EXAMPLE" "$LOCAL_ENV_FILE"
fi

"$VENV_DIR/bin/python" - <<PY
from pathlib import Path
path = Path(r"$LOCAL_ENV_FILE")
lines = []
for raw in path.read_text(encoding="utf-8").splitlines():
    if raw.startswith("KRONOS_PYTHON_BIN=") or raw.startswith("KRONOS_PROJECT_ROOT="):
        continue
    lines.append(raw)
lines.append(f"KRONOS_PYTHON_BIN={Path(r'$VENV_DIR') / 'bin' / 'python'}")
lines.append(f"KRONOS_PROJECT_ROOT={Path(r'$KRONOS_DIR')}")
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

echo "Kronos portable environment ready."
echo "Next: ./scripts/kronos/verify_kronos_env.sh"
```

- [ ] **Step 6: Create `scripts/kronos/verify_kronos_env.sh`**

Use this script body:

```bash
#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/common.sh
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

"$KRONOS_PYTHON_BIN" "$AGENT_ROOT/scripts/kronos/kronos_generate_signals.py" \
  --universe-file "$AGENT_ROOT/config/universe.txt" \
  --output-file "$AGENT_ROOT/state/runs/<date>/signals/kronos_signals.json" \
  --date "$(pt_date)" \
  --mock

echo "Kronos portable verification passed."
```

- [ ] **Step 7: Create `docs/setup/kronos-portable-setup.md`**

Use this outline:

```md
# Kronos Portable Setup

## Requirements

- macOS or Linux shell with `bash`
- `git`
- `python3`
- Codex installed separately

## Rebuild Steps

```bash
git clone <repo-url>
cd trading
chmod +x scripts/*.sh
./scripts/kronos/setup_kronos_env.sh
./scripts/kronos/verify_kronos_env.sh
```

## Manual Authentication Steps

```bash
codex login
codex mcp add robinhood-trading --url https://agent.robinhood.com/mcp/trading
codex
/mcp
```

Complete Robinhood Agentic Account authentication on desktop.

## Validation

```bash
./scripts/safety/check_safety.sh
ALLOW_WEEKEND_RUN=1 KRONOS_USE_MOCK=1 ./scripts/kronos/run_kronos_premarket_scan.sh
ALLOW_WEEKEND_RUN=1 KRONOS_USE_MOCK=1 CODEX_EXEC_DRY_RUN=1 ./scripts/entrypoints/run_premarket.sh
```
```

- [ ] **Step 8: Re-run the tests and verify artifact checks pass**

Run: `python3 -m unittest tests/test_kronos_generate_signals.py -v`

Expected: PASS for the artifact existence tests.

- [ ] **Step 9: Commit setup and verification assets**

```bash
git add config/runtime.env.local.example requirements-kronos-extra.txt scripts/kronos/setup_kronos_env.sh scripts/kronos/verify_kronos_env.sh docs/setup/kronos-portable-setup.md tests/test_kronos_generate_signals.py
git commit -m "feat: add portable Kronos setup scripts"
```

### Task 3: Implement the Kronos Signal Generator and Runner

**Files:**
- Create: `scripts/kronos/kronos_generate_signals.py`
- Create: `scripts/kronos/run_kronos_premarket_scan.sh`
- Modify: `tests/test_kronos_generate_signals.py`

- [ ] **Step 1: Add failing tests for mock signal generation and shell runner output**

Append:

```python
import json
import os
import subprocess
import sys
import tempfile

SCRIPT_PATH = REPO_ROOT / "scripts" / "kronos_generate_signals.py"
RUNNER_PATH = REPO_ROOT / "scripts" / "run_kronos_premarket_scan.sh"


class KronosGenerateSignalsTests(unittest.TestCase):
    def test_generate_mock_signals_writes_expected_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            universe = tmp / "universe.txt"
            output = tmp / "kronos_signals.json"
            universe.write_text("NVDA\nPLTR\n# comment\nNVDA\n", encoding="utf-8")

            cmd = [
                sys.executable,
                str(SCRIPT_PATH),
                "--universe-file",
                str(universe),
                "--output-file",
                str(output),
                "--date",
                "2026-06-13",
                "--mock",
            ]
            subprocess.run(cmd, check=True, cwd=REPO_ROOT)

            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["date"], "2026-06-13")
            self.assertEqual(payload["timeframe"], "30m")
            self.assertEqual(payload["horizon_bars"], 8)
            self.assertEqual(sorted(payload["symbols"].keys()), ["NVDA", "PLTR"])
            self.assertEqual(payload["model"]["mode"], "inference_only_mock")

    def test_rejects_predictions_for_symbols_outside_universe(self) -> None:
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        import kronos_generate_signals as mod

        with self.assertRaises(ValueError):
            mod.validate_signal_symbols({"NVDA"}, {"TSLA": {}})


class KronosRunnerTests(unittest.TestCase):
    def test_mock_runner_writes_repo_state_file(self) -> None:
        state_file = REPO_ROOT / "state" / "kronos_signals.json"
        if state_file.exists():
            state_file.unlink()

        env = os.environ.copy()
        env.update({"ALLOW_WEEKEND_RUN": "1", "KRONOS_USE_MOCK": "1"})
        subprocess.run(["bash", str(RUNNER_PATH)], check=True, cwd=REPO_ROOT, env=env)

        payload = json.loads(state_file.read_text(encoding="utf-8"))
        self.assertIn("symbols", payload)
        self.assertIn("generated_at", payload)
```

- [ ] **Step 2: Run the tests and verify they fail because generator and runner do not exist yet**

Run: `python3 -m unittest tests/test_kronos_generate_signals.py -v`

Expected: FAIL with missing file or import errors for the generator and runner tests.

- [ ] **Step 3: Create `scripts/kronos/kronos_generate_signals.py` with mock and live modes**

Use this file body:

```python
#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe-file", required=True)
    parser.add_argument("--output-file", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--mock", action="store_true")
    return parser.parse_args()


def load_universe(path: Path) -> list[str]:
    symbols: list[str] = []
    seen: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip().upper()
        if not line or line in seen:
            continue
        seen.add(line)
        symbols.append(line)
    if not symbols:
        raise ValueError("universe file produced zero symbols")
    return symbols


def validate_signal_symbols(universe_symbols: set[str], signal_map: dict[str, object]) -> None:
    extra = set(signal_map) - universe_symbols
    if extra:
        raise ValueError(f"signals contained symbols outside universe: {sorted(extra)}")


def build_mock_payload(symbols: list[str], run_date: str, source_universe: str) -> dict[str, object]:
    signal_map = {}
    for index, symbol in enumerate(symbols):
        signal_map[symbol] = {
            "direction_bias": "bullish" if index == 0 else "neutral",
            "confidence": 0.72 if index == 0 else 0.61,
            "predicted_return_bps": 180 - (index * 25),
            "predicted_volatility_bps": 220 + (index * 10),
            "path_summary": "up_then_consolidate" if index == 0 else "mixed_range",
            "setup_bias": "breakout" if index == 0 else "chop",
            "risk_flags": [],
            "reason": f"mock Kronos signal for {symbol}",
        }
    validate_signal_symbols(set(symbols), signal_map)
    return {
        "date": run_date,
        "generated_at": datetime.now().astimezone().isoformat(),
        "timeframe": os.environ.get("KRONOS_TIMEFRAME", "30m"),
        "horizon_bars": int(os.environ.get("KRONOS_HORIZON_BARS", "8")),
        "source_universe": source_universe,
        "model": {
            "name": os.environ.get("KRONOS_MODEL_NAME", "NeoQuasar/Kronos-small"),
            "tokenizer": os.environ.get("KRONOS_TOKENIZER_NAME", "NeoQuasar/Kronos-Tokenizer-base"),
            "mode": "inference_only_mock",
        },
        "data_status": "ok",
        "symbols": signal_map,
        "notes": "mock output for portable setup validation",
    }


def build_live_payload(symbols: list[str], run_date: str, source_universe: str) -> dict[str, object]:
    import pandas as pd
    import yfinance as yf

    sys.path.insert(0, os.environ["KRONOS_PROJECT_ROOT"])
    from model import Kronos, KronosPredictor, KronosTokenizer

    model_name = os.environ.get("KRONOS_MODEL_NAME", "NeoQuasar/Kronos-small")
    tokenizer_name = os.environ.get("KRONOS_TOKENIZER_NAME", "NeoQuasar/Kronos-Tokenizer-base")
    timeframe = os.environ.get("KRONOS_TIMEFRAME", "30m")
    lookback = int(os.environ.get("KRONOS_LOOKBACK_BARS", "400"))
    pred_len = int(os.environ.get("KRONOS_HORIZON_BARS", "8"))
    tokenizer = KronosTokenizer.from_pretrained(tokenizer_name)
    model = Kronos.from_pretrained(model_name)
    predictor = KronosPredictor(model, tokenizer, max_context=512)

    interval_map = {
        "30m": ("30m", "60d", "30min"),
        "1h": ("60m", "730d", "60min"),
        "1d": ("1d", "5y", "1D"),
    }
    interval, period, future_freq = interval_map[timeframe]
    signals = {}
    failures = []

    for symbol in symbols:
        try:
            history = yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=False)
            if history.empty:
                raise ValueError("no market data returned")
            history = history.rename(columns=str.lower).reset_index()
            history = history.rename(columns={history.columns[0]: "timestamps"})
            for column in ["open", "high", "low", "close"]:
                if column not in history.columns:
                    raise ValueError(f"missing column {column}")
            if "volume" not in history.columns:
                history["volume"] = 0
            if "amount" not in history.columns:
                history["amount"] = 0

            x_df = history.tail(lookback)[["open", "high", "low", "close", "volume", "amount"]]
            x_timestamp = history.tail(lookback)["timestamps"]
            last_ts = pd.to_datetime(x_timestamp.iloc[-1])
            y_timestamp = pd.date_range(last_ts, periods=pred_len + 1, freq=future_freq)[1:]
            pred_df = predictor.predict(
                df=x_df,
                x_timestamp=x_timestamp,
                y_timestamp=y_timestamp,
                pred_len=pred_len,
                T=float(os.environ.get("KRONOS_TEMPERATURE", "1.0")),
                top_p=float(os.environ.get("KRONOS_TOP_P", "0.9")),
                sample_count=int(os.environ.get("KRONOS_SAMPLE_COUNT", "1")),
            )

            last_close = float(x_df["close"].iloc[-1])
            forecast_close = float(pred_df["close"].iloc[-1])
            return_bps = int(round(((forecast_close - last_close) / last_close) * 10000))
            vol_bps = max(1, int(round(pred_df["close"].pct_change().fillna(0).std() * 10000)))
            confidence = round(min(0.95, max(0.05, abs(return_bps) / max(vol_bps, 50))), 2)

            if return_bps >= 75:
                direction_bias = "bullish"
                setup_bias = "breakout"
                path_summary = "up_then_consolidate"
            elif return_bps <= -75:
                direction_bias = "bearish"
                setup_bias = "avoid"
                path_summary = "downside_extension"
            else:
                direction_bias = "neutral"
                setup_bias = "chop"
                path_summary = "mixed_range"

            signals[symbol] = {
                "direction_bias": direction_bias,
                "confidence": confidence,
                "predicted_return_bps": return_bps,
                "predicted_volatility_bps": vol_bps,
                "path_summary": path_summary,
                "setup_bias": setup_bias,
                "risk_flags": [] if vol_bps < 300 else ["high_forecast_volatility"],
                "reason": f"Kronos forecast from {timeframe} data",
            }
        except Exception as exc:
            failures.append(f"{symbol}: {exc}")

    validate_signal_symbols(set(symbols), signals)
    return {
        "date": run_date,
        "generated_at": datetime.now().astimezone().isoformat(),
        "timeframe": timeframe,
        "horizon_bars": pred_len,
        "source_universe": source_universe,
        "model": {
            "name": model_name,
            "tokenizer": tokenizer_name,
            "mode": "inference_only",
        },
        "data_status": "ok" if signals and not failures else "partial" if signals else "failed",
        "symbols": signals,
        "notes": "; ".join(failures[:5]) if failures else "live Kronos output",
    }


def main() -> int:
    args = parse_args()
    universe_file = Path(args.universe_file)
    output_file = Path(args.output_file)
    symbols = load_universe(universe_file)
    payload = build_mock_payload(symbols, args.date, str(universe_file)) if args.mock else build_live_payload(symbols, args.date, str(universe_file))
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"kronos signals written: {output_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Create `scripts/kronos/run_kronos_premarket_scan.sh`**

Use this file body:

```bash
#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/common.sh
source "$SCRIPT_DIR/common.sh"

acquire_lock "kronos_premarket_scan"

if ! is_weekday_pt && [[ "${ALLOW_WEEKEND_RUN:-0}" != "1" ]]; then
  log_line "kronos_premarket_scan weekend skip."
  exit 0
fi

OUTPUT_FILE="$AGENT_ROOT/state/runs/<date>/signals/kronos_signals.json"
RUN_DATE="$(pt_date)"

cmd=(
  "$KRONOS_PYTHON_BIN"
  "$AGENT_ROOT/scripts/kronos/kronos_generate_signals.py"
  "--universe-file" "$AGENT_ROOT/config/universe.txt"
  "--output-file" "$OUTPUT_FILE"
  "--date" "$RUN_DATE"
)

if [[ "${KRONOS_USE_MOCK:-0}" == "1" ]]; then
  cmd+=("--mock")
fi

log_line "kronos_premarket_scan starting timeframe=$KRONOS_TIMEFRAME model=$KRONOS_MODEL_NAME"
"${cmd[@]}" >> "$RUN_LOG" 2>> "$ERROR_LOG"
log_line "kronos_premarket_scan completed output=$OUTPUT_FILE"
```

- [ ] **Step 5: Re-run the tests and verify the generator and runner tests pass**

Run: `python3 -m unittest tests/test_kronos_generate_signals.py -v`

Expected: PASS for the mock generation, symbol validation, and runner output tests.

- [ ] **Step 6: Commit generator and runner**

```bash
git add scripts/kronos/kronos_generate_signals.py scripts/kronos/run_kronos_premarket_scan.sh tests/test_kronos_generate_signals.py
git commit -m "feat: add Kronos signal generator and runner"
```

### Task 4: Wire Kronos into Premarket and Safety Checks

**Files:**
- Modify: `scripts/entrypoints/run_premarket.sh`
- Modify: `prompts/premarket/final_research.txt`
- Modify: `scripts/safety/check_safety.sh`

- [ ] **Step 1: Add a failing assertion for premarket prompt wiring**

Append:

```python
class PromptWiringTests(unittest.TestCase):
    def test_premarket_prompt_mentions_kronos_signal_file(self) -> None:
        prompt = (REPO_ROOT / "prompts" / "premarket_research.txt").read_text(encoding="utf-8")
        self.assertIn("state/runs/<date>/signals/kronos_signals.json", prompt)
        self.assertIn("kronos_signal_status", prompt)
```

- [ ] **Step 2: Run the tests and verify prompt wiring fails before edits**

Run: `python3 -m unittest tests/test_kronos_generate_signals.py -v`

Expected: FAIL in `test_premarket_prompt_mentions_kronos_signal_file`.

- [ ] **Step 3: Update `scripts/entrypoints/run_premarket.sh` to execute Kronos after DSA**

Insert:

```bash
if [[ "${ENABLE_KRONOS_SIGNAL_LAYER:-1}" == "1" ]]; then
  if ! "$SCRIPT_DIR/run_kronos_premarket_scan.sh"; then
    log_line "kronos_premarket_scan failed; continuing with main premarket research."
  fi
fi
```

directly before:

```bash
run_codex_prompt "premarket" "$AGENT_ROOT/prompts/premarket/final_research.txt"
```

- [ ] **Step 4: Update `prompts/premarket/final_research.txt` to read and constrain Kronos**

Add to the file-reading section:

```text
- `state/runs/<date>/signals/kronos_signals.json` if it exists and is for today
```

Insert this task block after the DSA block:

```text
6. Read `state/runs/<date>/signals/kronos_signals.json` if present. Treat it as a non-binding forecast layer only:
   - It may improve candidate ranking, setup bias selection, and watch/block context.
   - It must never override `config/risk.md`, `config/risk_tiers.json`, Robinhood MCP account checks, tradability checks, daily caps, or the daily plan schema.
   - If it is missing, stale, invalid, or partial, continue the main scan and record `kronos_signal_status` accordingly.
```

Update the JSON schema:

```json
"data_status": {
  "robinhood_mcp": "ok|failed|partial",
  "quotes": "ok|failed|partial",
  "market_calendar": "ok|uncertain",
  "dsa_signal_status": "ok|missing|stale|partial|failed",
  "kronos_signal_status": "ok|missing|stale|partial|failed",
  "missing_or_stale": []
}
```

And add these fields under each `symbol_scores` entry:

```json
"kronos_direction_bias": "bullish|bearish|neutral|missing",
"kronos_confidence": 0.0,
"kronos_setup_bias": "breakout|pullback|chop|avoid|missing",
```

- [ ] **Step 5: Update `scripts/safety/check_safety.sh` for portable setup visibility**

Add:

```bash
if [[ -f "$AGENT_ROOT/scripts/kronos/kronos_generate_signals.py" ]] \
  && [[ -f "$AGENT_ROOT/scripts/kronos/run_kronos_premarket_scan.sh" ]] \
  && rg -q 'state/runs/<date>/signals/kronos_signals.json' "$AGENT_ROOT/prompts/premarket/final_research.txt"; then
  echo "  - Kronos signal layer is configured and wired into premarket: ok"
else
  echo "  - WARNING: Kronos signal layer is incomplete or not wired into premarket."
fi

if [[ -f "$AGENT_ROOT/config/runtime.env.local.example" ]] \
  && rg -q '^ENABLE_KRONOS_SIGNAL_LAYER=' "$AGENT_ROOT/config/runtime.env"; then
  echo "  - Portable Kronos setup files found: ok"
else
  echo "  - WARNING: portable Kronos setup files missing."
fi
```

- [ ] **Step 6: Re-run the tests and verify prompt wiring now passes**

Run: `python3 -m unittest tests/test_kronos_generate_signals.py -v`

Expected: PASS for `test_premarket_prompt_mentions_kronos_signal_file`.

- [ ] **Step 7: Commit wiring and safety checks**

```bash
git add scripts/entrypoints/run_premarket.sh prompts/premarket/final_research.txt scripts/safety/check_safety.sh tests/test_kronos_generate_signals.py
git commit -m "feat: wire Kronos into premarket planning"
```

### Task 5: Update Operator Docs and Validate the Portable Flow

**Files:**
- Modify: `README.md`
- Modify: `tests/test_kronos_generate_signals.py`

- [ ] **Step 1: Add a doc regression test for portable setup commands**

Append:

```python
class DocumentationTests(unittest.TestCase):
    def test_readme_mentions_portable_kronos_setup(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("./scripts/kronos/setup_kronos_env.sh", readme)
        self.assertIn("./scripts/kronos/verify_kronos_env.sh", readme)
```

- [ ] **Step 2: Run the tests and verify the README check fails before the README edit**

Run: `python3 -m unittest tests/test_kronos_generate_signals.py -v`

Expected: FAIL in `test_readme_mentions_portable_kronos_setup`.

- [ ] **Step 3: Update `README.md` with a portable setup section**

Add this section after `## Setup`:

```md
## Portable Kronos Setup

To rebuild the Kronos environment on a new machine:

```bash
git clone <repo-url>
cd trading
chmod +x scripts/*.sh
./scripts/kronos/setup_kronos_env.sh
./scripts/kronos/verify_kronos_env.sh
```

Manual authentication still required:

```bash
codex login
codex mcp add robinhood-trading --url https://agent.robinhood.com/mcp/trading
codex
/mcp
```

Then validate:

```bash
./scripts/safety/check_safety.sh
ALLOW_WEEKEND_RUN=1 KRONOS_USE_MOCK=1 ./scripts/kronos/run_kronos_premarket_scan.sh
ALLOW_WEEKEND_RUN=1 KRONOS_USE_MOCK=1 CODEX_EXEC_DRY_RUN=1 ./scripts/entrypoints/run_premarket.sh
```
```

- [ ] **Step 4: Re-run the tests and verify the README check now passes**

Run: `python3 -m unittest tests/test_kronos_generate_signals.py -v`

Expected: PASS for the README test.

- [ ] **Step 5: Run the setup script on the current machine**

Run: `./scripts/kronos/setup_kronos_env.sh`

Expected:
- `.venv-kronos` exists
- `.vendor/kronos` exists
- `config/runtime.env.local` exists
- script prints `Kronos portable environment ready.`

- [ ] **Step 6: Run the verification script**

Run: `./scripts/kronos/verify_kronos_env.sh`

Expected:
- prints `python imports ok`
- writes `state/runs/<date>/signals/kronos_signals.json` in mock mode
- prints `Kronos portable verification passed.`

- [ ] **Step 7: Run safety and dry-run checks**

Run:

```bash
./scripts/safety/check_safety.sh
ALLOW_WEEKEND_RUN=1 KRONOS_USE_MOCK=1 ./scripts/kronos/run_kronos_premarket_scan.sh
ALLOW_WEEKEND_RUN=1 KRONOS_USE_MOCK=1 CODEX_EXEC_DRY_RUN=1 ./scripts/entrypoints/run_premarket.sh
```

Expected:
- `check_safety.sh` reports portable Kronos setup files and premarket wiring as ok
- `state/runs/<date>/signals/kronos_signals.json` is produced
- `logs/codex_runs.log` shows DSA, then Kronos, then premarket

- [ ] **Step 8: Run the full focused test suite one final time**

Run: `python3 -m unittest tests/test_kronos_generate_signals.py -v`

Expected: PASS for all tests in the file.

- [ ] **Step 9: Commit docs and final validation changes**

```bash
git add README.md tests/test_kronos_generate_signals.py
git commit -m "docs: add portable Kronos rebuild workflow"
```

## Spec Coverage Check

- Portable install paths: covered by Task 1 and Task 2.
- Fixed Kronos version and repo-local bootstrap: covered by Task 2.
- Local path isolation from git: covered by Task 1 and Task 2.
- Mock-before-auth workflow: covered by Task 3 and Task 5.
- Premarket-only advisory integration: covered by Task 3 and Task 4.
- Non-blocking runtime behavior: covered by Task 3 and Task 4.
- Operator docs and rebuild commands: covered by Task 2 and Task 5.

## Self-Review Notes

- The plan matches the current spec and no longer assumes an external user-managed Kronos install.
- File paths, commands, and commit boundaries are concrete.
- Setup is strict-fail, runtime is safe-degrade.
- The plan remains scoped to one working subsystem: portable premarket Kronos integration.
