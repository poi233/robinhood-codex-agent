# Premarket Skill Feed Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a repo-owned skill pack, a portable market-feed collector, and a dedicated technical-analysis layer that feeds execution-aware price levels into the existing premarket and intraday workflows without disturbing the already-wired Kronos premarket layer.

**Architecture:** Keep `.agents/skills/` as the repository source of truth, copy those skills into both `$HOME/.agents/skills` and `~/.codex/skills`, preserve the current `DSA -> Kronos -> main premarket` ordering, insert normalized market artifacts under `state/runs/<date>/market_feed/` after the Kronos layer, run a separate Codex technical-analysis prompt that writes `state/runs/<date>/signals/technical_signals.json`, then let the main premarket and intraday prompts consume that contract while preserving long-only execution rules.

**Tech Stack:** Bash, Python 3.11, `unittest`, `json`, `pathlib`, `subprocess`, `yfinance`, `pandas`, `matplotlib`, Codex prompts, local JSON state files

---

## File Map

- Create: `.agents/skills/chan-structure-trading/**`
- Create: `.agents/skills/brooks-trading-range-price-action/**`
- Create: `.agents/skills/equity-fundamentals-analysis/**`
- Create: `.agents/skills/trading-research-casebook-maintenance/**`
- Create: `docs/setup/repo-skills.md`
- Create: `docs/setup/market-feed.md`
- Create: `prompts/technical/research.txt`
- Create: `scripts/skills/install_repo_skills.sh`
- Create: `scripts/skills/verify_repo_skills.sh`
- Create: `scripts/data/collect_market_feed.py`
- Create: `scripts/data/run_market_feed_collection.sh`
- Create: `scripts/data/run_technical_research.sh`
- Create: `scripts/data/run_symbol_research.sh`
- Create: `tests/test_install_repo_skills.py`
- Create: `tests/test_collect_market_feed.py`
- Create: `tests/test_technical_signal_schema.py`
- Modify: `.gitignore`
- Modify: `README.md`
- Modify: `config/runtime.env`
- Modify: `scripts/safety/check_safety.sh`
- Modify: `scripts/lib/common.sh`
- Modify: `scripts/entrypoints/run_premarket.sh`
- Modify: `prompts/intraday/check.txt`
- Modify: `prompts/premarket/final_research.txt`

## Responsibility Split

- `.agents/skills/**`: repo-owned skill source of truth.
- `scripts/skills/install_repo_skills.sh`: copy repo skills into both user-level skill destinations.
- `scripts/skills/verify_repo_skills.sh`: verify installed skills are complete copies.
- `scripts/lib/common.sh`: shared runtime flags, helper paths, and prompt runtime block fields.
- `scripts/data/collect_market_feed.py`: deterministic artifact collector for OHLCV, charts, news, earnings, and filings.
- `scripts/data/run_market_feed_collection.sh`: shell entrypoint for scheduled collector runs.
- `prompts/technical/research.txt`: explicit technical-analysis prompt that uses repo skills and writes `state/runs/<date>/signals/technical_signals.json`.
- `scripts/data/run_technical_research.sh`: scheduled and manual runner for the technical-analysis step.
- `prompts/premarket/final_research.txt`: consume technical signals instead of re-deriving all raw chart interpretation.
- `prompts/intraday/check.txt`: consume key price levels and no-trade zones from `state/runs/<date>/signals/technical_signals.json`.
- `scripts/data/run_symbol_research.sh`: ad hoc single-symbol collector + technical-analysis path.
- `tests/test_install_repo_skills.py`: install/verify script contract.
- `tests/test_collect_market_feed.py`: collector artifact contract and mock mode.
- `tests/test_technical_signal_schema.py`: technical signal schema and prompt wiring.
- `docs/setup/*.md` and `README.md`: operator setup and usage documentation.

## Implementation Notes

- Keep `.agents/skills/` committed. Do not ignore it.
- Keep `state/market_feed/` ignored the same way other runtime state is ignored.
- Add a deterministic `--mock` collector mode so tests do not depend on live network calls.
- Keep `short_setup` strictly informational for existing long positions. It must not authorize short selling.
- Keep `trading-research-casebook-maintenance` out of the critical trading path.
- Do not remove, reorder ahead of DSA, or otherwise weaken the current Kronos integration while adding the skill-feed pipeline.

### Task 1: Add Repo-Owned Skills and Install/Verify Scripts

**Files:**
- Create: `.agents/skills/chan-structure-trading/**`
- Create: `.agents/skills/brooks-trading-range-price-action/**`
- Create: `.agents/skills/equity-fundamentals-analysis/**`
- Create: `.agents/skills/trading-research-casebook-maintenance/**`
- Create: `scripts/skills/install_repo_skills.sh`
- Create: `scripts/skills/verify_repo_skills.sh`
- Create: `tests/test_install_repo_skills.py`

- [ ] **Step 1: Write failing install-script contract tests**

Create `tests/test_install_repo_skills.py` with:

```python
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SCRIPT = REPO_ROOT / "scripts" / "install_repo_skills.sh"
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_repo_skills.sh"


class RepoSkillInstallTests(unittest.TestCase):
    def test_install_and_verify_scripts_exist(self) -> None:
        self.assertTrue(INSTALL_SCRIPT.exists())
        self.assertTrue(VERIFY_SCRIPT.exists())

    def test_install_script_copies_repo_skills_into_both_destinations(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            agents_home = tmp / ".agents" / "skills"
            codex_home = tmp / ".codex" / "skills"
            env = {
                **os.environ,
                "HOME": str(tmp),
                "REPO_SKILL_TARGETS": f"{agents_home}:{codex_home}",
            }

            result = subprocess.run(
                ["bash", str(INSTALL_SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            for target in (agents_home, codex_home):
                self.assertTrue((target / "chan-structure-trading" / "SKILL.md").exists())
                self.assertTrue((target / "brooks-trading-range-price-action" / "references").exists())
                self.assertTrue((target / "trading-research-casebook-maintenance" / "case-update-log.md").exists())
```

- [ ] **Step 2: Run the tests and verify they fail because the scripts and repo-owned skill pack do not exist yet**

Run: `python3 -m unittest tests/test_install_repo_skills.py -v`

Expected: FAIL on missing script files and missing `.agents/skills/**`.

- [ ] **Step 3: Copy the four skill directories into `.agents/skills/`**

Create the repo skill directories by copying the full source directories:

```bash
mkdir -p .agents/skills
cp -R "$HOME/.codex/skills/chan-structure-trading" .agents/skills/
cp -R "$HOME/.codex/skills/brooks-trading-range-price-action" .agents/skills/
cp -R "$HOME/.codex/skills/equity-fundamentals-analysis" .agents/skills/
cp -R "$HOME/.codex/skills/trading-research-casebook-maintenance" .agents/skills/
```

- [ ] **Step 4: Create the installer script**

Create `scripts/skills/install_repo_skills.sh` with:

```bash
#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_ROOT="$REPO_ROOT/.agents/skills"

if [[ ! -d "$SOURCE_ROOT" ]]; then
  echo "missing repo skill source: $SOURCE_ROOT" >&2
  exit 1
fi

if [[ -n "${REPO_SKILL_TARGETS:-}" ]]; then
  IFS=':' read -r -a TARGETS <<< "$REPO_SKILL_TARGETS"
else
  TARGETS=("$HOME/.agents/skills" "$HOME/.codex/skills")
fi

SKILLS=(
  chan-structure-trading
  brooks-trading-range-price-action
  equity-fundamentals-analysis
  trading-research-casebook-maintenance
)

for target in "${TARGETS[@]}"; do
  mkdir -p "$target"
  for skill in "${SKILLS[@]}"; do
    src="$SOURCE_ROOT/$skill"
    dst="$target/$skill"
    [[ -f "$src/SKILL.md" ]] || { echo "missing SKILL.md in $src" >&2; exit 1; }
    rm -rf "$dst"
    cp -R "$src" "$dst"
  done
done

echo "installed repo skills into ${TARGETS[*]}"
```

- [ ] **Step 5: Create the verifier script**

Create `scripts/skills/verify_repo_skills.sh` with:

```bash
#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_ROOT="$REPO_ROOT/.agents/skills"
SKILLS=(
  chan-structure-trading
  brooks-trading-range-price-action
  equity-fundamentals-analysis
  trading-research-casebook-maintenance
)

TARGETS=("$HOME/.agents/skills" "$HOME/.codex/skills")
status=0

for target in "${TARGETS[@]}"; do
  echo "checking $target"
  for skill in "${SKILLS[@]}"; do
    dst="$target/$skill"
    if [[ ! -f "$dst/SKILL.md" ]]; then
      echo "missing $dst/SKILL.md" >&2
      status=1
      continue
    fi
    if [[ -d "$SOURCE_ROOT/$skill/references" && ! -d "$dst/references" ]]; then
      echo "missing $dst/references" >&2
      status=1
    fi
    if [[ -d "$SOURCE_ROOT/$skill/casebook" && ! -d "$dst/casebook" ]]; then
      echo "missing $dst/casebook" >&2
      status=1
    fi
  done
done

exit "$status"
```

- [ ] **Step 6: Re-run the tests and verify the install contract passes**

Run: `python3 -m unittest tests/test_install_repo_skills.py -v`

Expected: PASS for both script existence and copy behavior.

- [ ] **Step 7: Commit the skill-pack and install tooling**

```bash
git add .agents/skills scripts/skills/install_repo_skills.sh scripts/skills/verify_repo_skills.sh tests/test_install_repo_skills.py
git commit -m "feat: add repo-owned trading skill pack"
```

### Task 2: Add Shared Runtime Flags and State Paths

**Files:**
- Modify: `.gitignore`
- Modify: `config/runtime.env`
- Modify: `scripts/lib/common.sh`

- [ ] **Step 1: Add failing coverage for new runtime exports**

Extend `tests/test_install_repo_skills.py` with:

```python
class CommonRuntimeSkillFeedTests(unittest.TestCase):
    def test_common_sh_exports_market_feed_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "config").mkdir()
            (tmp / "scripts").mkdir()
            (tmp / "config" / "runtime.env").write_text("TRADING_MODE=paper\n", encoding="utf-8")
            (tmp / "scripts" / "common.sh").write_text(
                (REPO_ROOT / "scripts" / "common.sh").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    "bash",
                    "-lc",
                    (
                        f"cd {tmp} && source scripts/lib/common.sh && "
                        "printf '%s\n%s\n%s' "
                        "\"$ENABLE_MARKET_FEED_LAYER\" "
                        "\"$MARKET_FEED_DIR\" "
                        "\"$TECHNICAL_SIGNALS_FILE\""
                    ),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertIn("/state/market_feed/", result.stdout)
            self.assertIn("/state/runs/<date>/signals/technical_signals.json", result.stdout)
```

- [ ] **Step 2: Run the test and verify it fails before the new exports exist**

Run: `python3 -m unittest tests/test_install_repo_skills.py -v`

Expected: FAIL because `ENABLE_MARKET_FEED_LAYER`, `MARKET_FEED_DIR`, and `TECHNICAL_SIGNALS_FILE` are not exported yet.

- [ ] **Step 3: Update `.gitignore` to keep generated market-feed artifacts out of git**

Add:

```gitignore
.superpowers/
```

Keep existing `state/*` ignore rules; no extra ignore is needed for `state/market_feed/**`.

- [ ] **Step 4: Add committed defaults to `config/runtime.env`**

Append:

```bash
# Optional market-feed and technical signal layers.
ENABLE_MARKET_FEED_LAYER=1
ENABLE_TECHNICAL_SIGNAL_LAYER=1
MARKET_FEED_PYTHON_BIN=python3
MARKET_FEED_TIMEFRAMES=1w,1d,1h,15m
MARKET_FEED_NEWS_LIMIT=5
TECHNICAL_SIGNALS_FILE=state/runs/<date>/signals/technical_signals.json
```

- [ ] **Step 5: Export new shared paths from `scripts/lib/common.sh`**

Add override variables:

```bash
OVERRIDE_ENABLE_MARKET_FEED_LAYER="${ENABLE_MARKET_FEED_LAYER-}"
OVERRIDE_ENABLE_TECHNICAL_SIGNAL_LAYER="${ENABLE_TECHNICAL_SIGNAL_LAYER-}"
OVERRIDE_MARKET_FEED_PYTHON_BIN="${MARKET_FEED_PYTHON_BIN-}"
OVERRIDE_MARKET_FEED_TIMEFRAMES="${MARKET_FEED_TIMEFRAMES-}"
OVERRIDE_MARKET_FEED_NEWS_LIMIT="${MARKET_FEED_NEWS_LIMIT-}"
OVERRIDE_TECHNICAL_SIGNALS_FILE="${TECHNICAL_SIGNALS_FILE-}"
```

Apply defaults and exports:

```bash
ENABLE_MARKET_FEED_LAYER="${ENABLE_MARKET_FEED_LAYER:-1}"
ENABLE_TECHNICAL_SIGNAL_LAYER="${ENABLE_TECHNICAL_SIGNAL_LAYER:-1}"
MARKET_FEED_PYTHON_BIN="${MARKET_FEED_PYTHON_BIN:-python3}"
MARKET_FEED_TIMEFRAMES="${MARKET_FEED_TIMEFRAMES:-1w,1d,1h,15m}"
MARKET_FEED_NEWS_LIMIT="${MARKET_FEED_NEWS_LIMIT:-5}"
MARKET_FEED_DIR="${AGENT_ROOT}/state/market_feed/$(pt_date)"
TECHNICAL_SIGNALS_FILE="${TECHNICAL_SIGNALS_FILE:-state/runs/<date>/signals/technical_signals.json}"
TECHNICAL_SIGNALS_PATH="${AGENT_ROOT}/${TECHNICAL_SIGNALS_FILE}"

export ENABLE_MARKET_FEED_LAYER
export ENABLE_TECHNICAL_SIGNAL_LAYER
export MARKET_FEED_PYTHON_BIN
export MARKET_FEED_TIMEFRAMES
export MARKET_FEED_NEWS_LIMIT
export MARKET_FEED_DIR
export TECHNICAL_SIGNALS_FILE
export TECHNICAL_SIGNALS_PATH
```

Extend `build_runtime_block()` with:

```text
ENABLE_MARKET_FEED_LAYER=$ENABLE_MARKET_FEED_LAYER
ENABLE_TECHNICAL_SIGNAL_LAYER=$ENABLE_TECHNICAL_SIGNAL_LAYER
MARKET_FEED_DIR=$MARKET_FEED_DIR
TECHNICAL_SIGNALS_PATH=$TECHNICAL_SIGNALS_PATH
```

- [ ] **Step 6: Re-run the runtime test and verify the new exports are present**

Run: `python3 -m unittest tests/test_install_repo_skills.py -v`

Expected: PASS for `test_common_sh_exports_market_feed_paths`.

- [ ] **Step 7: Commit the runtime-layer changes**

```bash
git add .gitignore config/runtime.env scripts/lib/common.sh tests/test_install_repo_skills.py
git commit -m "feat: add runtime config for skill feed pipeline"
```

### Task 3: Implement the Market-Feed Collector and Artifact Contract

**Files:**
- Create: `scripts/data/collect_market_feed.py`
- Create: `scripts/data/run_market_feed_collection.sh`
- Create: `tests/test_collect_market_feed.py`

- [ ] **Step 1: Write failing collector contract tests**

Create `tests/test_collect_market_feed.py` with:

```python
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
COLLECTOR = REPO_ROOT / "scripts" / "collect_market_feed.py"


class MarketFeedCollectorTests(unittest.TestCase):
    def test_mock_mode_writes_manifest_and_symbol_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            universe = tmp / "universe.txt"
            output_dir = tmp / "market_feed"
            universe.write_text("NVDA\nSPY\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(COLLECTOR),
                    "--universe-file",
                    str(universe),
                    "--output-dir",
                    str(output_dir),
                    "--date",
                    "2026-06-13",
                    "--mock",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["data_status"], "ok")
            self.assertEqual(sorted(manifest["completed_symbols"]), ["NVDA", "SPY"])
            self.assertTrue((output_dir / "ohlcv" / "NVDA" / "daily.json").exists())
            self.assertTrue((output_dir / "charts" / "SPY" / "daily.png").exists())
            self.assertTrue((output_dir / "news" / "market_summary.json").exists())
```

- [ ] **Step 2: Run the test and verify it fails because the collector does not exist**

Run: `python3 -m unittest tests/test_collect_market_feed.py -v`

Expected: FAIL on missing `scripts/data/collect_market_feed.py`.

- [ ] **Step 3: Implement the collector module with deterministic mock mode**

Create `scripts/data/collect_market_feed.py` with this structure:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf


TIMEFRAME_MAP = {
    "1w": {"label": "weekly", "period": "3y", "interval": "1wk"},
    "1d": {"label": "daily", "period": "1y", "interval": "1d"},
    "1h": {"label": "hourly", "period": "60d", "interval": "60m"},
    "15m": {"label": "intraday_15m", "period": "30d", "interval": "15m"},
}


def parse_universe(path: Path) -> list[str]:
    return [
        line.strip().upper()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def write_chart(df: pd.DataFrame, output_path: Path, title: str) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True, height_ratios=[4, 1])
    axes[0].plot(df.index, df["Close"], label="Close", linewidth=1.2)
    axes[0].plot(df.index, df["Close"].rolling(20).mean(), label="MA20", linewidth=1.0)
    axes[0].plot(df.index, df["Close"].rolling(50).mean(), label="MA50", linewidth=1.0)
    axes[0].set_title(title)
    axes[0].legend(loc="upper left")
    axes[1].bar(df.index, df["Volume"])
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
```

Also add:

```python
def build_mock_frame() -> pd.DataFrame:
    index = pd.date_range("2026-05-01", periods=80, freq="D")
    close = pd.Series(range(80), index=index, dtype="float64") + 100.0
    return pd.DataFrame(
        {
            "Open": close - 0.5,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
            "Volume": 1_000_000,
        }
    )
```

And a manifest writer:

```python
def write_manifest(output_dir: Path, payload: dict) -> None:
    (output_dir / "manifest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
```

- [ ] **Step 4: Add the shell runner for scheduled use**

Create `scripts/data/run_market_feed_collection.sh` with:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

acquire_lock "market_feed"

if [[ "${ENABLE_MARKET_FEED_LAYER:-1}" != "1" ]]; then
  log_line "market_feed disabled; skipping."
  exit 0
fi

"$MARKET_FEED_PYTHON_BIN" "$AGENT_ROOT/scripts/data/collect_market_feed.py" \
  --universe-file "$AGENT_ROOT/config/universe.txt" \
  --output-dir "$MARKET_FEED_DIR" \
  --date "$(pt_date)"
```

- [ ] **Step 5: Re-run the collector test and verify mock mode produces the contract**

Run: `python3 -m unittest tests/test_collect_market_feed.py -v`

Expected: PASS for `test_mock_mode_writes_manifest_and_symbol_artifacts`.

- [ ] **Step 6: Commit the collector layer**

```bash
git add scripts/data/collect_market_feed.py scripts/data/run_market_feed_collection.sh tests/test_collect_market_feed.py
git commit -m "feat: add market feed collector"
```

### Task 4: Add Technical Research Prompt, Runner, and Signal Schema

**Files:**
- Create: `prompts/technical/research.txt`
- Create: `scripts/data/run_technical_research.sh`
- Create: `tests/test_technical_signal_schema.py`

- [ ] **Step 1: Write failing schema and prompt wiring tests**

Create `tests/test_technical_signal_schema.py` with:

```python
import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


class TechnicalPromptWiringTests(unittest.TestCase):
    def test_technical_prompt_exists_and_references_repo_skills(self) -> None:
        prompt = (REPO_ROOT / "prompts" / "technical_research.txt").read_text(encoding="utf-8")
        self.assertIn(".agents/skills/chan-structure-trading", prompt)
        self.assertIn(".agents/skills/brooks-trading-range-price-action", prompt)
        self.assertIn("state/runs/<date>/signals/technical_signals.json", prompt)

    def test_sample_schema_contains_dual_execution_scenarios(self) -> None:
        payload = {
            "symbols": {
                "NVDA": {
                    "long_setup": {"trigger_above": 0, "entry_zone": {"low": 0, "high": 0}},
                    "short_setup": {"trigger_below": 0, "entry_zone": {"low": 0, "high": 0}},
                    "no_trade_zone": {"low": 0, "high": 0, "reason": "range"},
                }
            }
        }
        self.assertIn("long_setup", payload["symbols"]["NVDA"])
        self.assertIn("short_setup", payload["symbols"]["NVDA"])
        self.assertIn("no_trade_zone", payload["symbols"]["NVDA"])
```

- [ ] **Step 2: Run the tests and verify they fail before the prompt and runner exist**

Run: `python3 -m unittest tests/test_technical_signal_schema.py -v`

Expected: FAIL because `prompts/technical/research.txt` is missing.

- [ ] **Step 3: Write the technical research prompt**

Create `prompts/technical/research.txt` with:

```text
You are my dedicated premarket technical research agent.

This run is research-only. Do not call `review_equity_order`, `place_equity_order`, `cancel_equity_order`, option tools, or any tool that changes account state.

Read these local files first:
- `config/universe.txt`
- `config/risk.md`
- `config/strategy.md`
- `config/runtime.env`
- `state/runs/<date>/signals/dsa_signals.json` if it exists
- `state/market_feed/<today>/manifest.json`
- `state/market_feed/<today>/charts/...`
- `state/market_feed/<today>/ohlcv/...`
- `state/market_feed/<today>/news/...`

Before analysis, read these repo-owned skills as the authoritative framework:
- `.agents/skills/chan-structure-trading/SKILL.md`
- `.agents/skills/brooks-trading-range-price-action/SKILL.md`
- `.agents/skills/equity-fundamentals-analysis/SKILL.md`

For each selected symbol, produce:
- `technical_phase`
- `technical_action`
- `key_levels`
- `long_setup`
- `short_setup`
- `no_trade_zone`
- `chan`
- `brooks`
- `fundamentals`
- `decision_rationale`
- `confidence`

Rules:
- `short_setup` is only for managing an existing long position. It is never permission to short.
- If structure is ambiguous, use `technical_action="observe"` or `technical_action="avoid"`.
- If price is in a noisy range, populate `no_trade_zone`.
- Always provide concrete price levels for triggers, invalidation, and targets when data quality allows.

Write `state/runs/<date>/signals/technical_signals.json` using the exact schema in the repo design spec.
Print a short stdout summary.
```

- [ ] **Step 4: Add the technical research runner**

Create `scripts/data/run_technical_research.sh` with:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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

run_codex_prompt "technical_research" "$AGENT_ROOT/prompts/technical/research.txt"
```

- [ ] **Step 5: Re-run the schema and wiring tests**

Run: `python3 -m unittest tests/test_technical_signal_schema.py -v`

Expected: PASS for prompt existence and dual-scenario schema checks.

- [ ] **Step 6: Commit the technical-analysis layer**

```bash
git add prompts/technical/research.txt scripts/data/run_technical_research.sh tests/test_technical_signal_schema.py
git commit -m "feat: add technical research layer"
```

### Task 5: Integrate Premarket, Intraday, and Safety Checks

**Files:**
- Modify: `scripts/entrypoints/run_premarket.sh`
- Modify: `scripts/entrypoints/run_intraday.sh`
- Modify: `scripts/safety/check_safety.sh`
- Modify: `prompts/premarket/final_research.txt`
- Modify: `prompts/intraday/check.txt`
- Modify: `tests/test_technical_signal_schema.py`

- [ ] **Step 1: Add failing wiring tests for premarket and intraday prompt consumption**

Extend `tests/test_technical_signal_schema.py` with:

```python
    def test_premarket_prompt_reads_technical_signals(self) -> None:
        prompt = (REPO_ROOT / "prompts" / "premarket_research.txt").read_text(encoding="utf-8")
        self.assertIn("state/runs/<date>/signals/technical_signals.json", prompt)
        self.assertIn("technical_action", prompt)

    def test_intraday_prompt_reads_key_levels(self) -> None:
        prompt = (REPO_ROOT / "prompts" / "intraday_check.txt").read_text(encoding="utf-8")
        self.assertIn("state/runs/<date>/signals/technical_signals.json", prompt)
        self.assertIn("long_setup", prompt)
        self.assertIn("short_setup", prompt)
        self.assertIn("no_trade_zone", prompt)
```

- [ ] **Step 2: Run the tests and verify the new wiring checks fail**

Run: `python3 -m unittest tests/test_technical_signal_schema.py -v`

Expected: FAIL because the current prompts do not reference the new technical signal file.

- [ ] **Step 3: Update `scripts/entrypoints/run_premarket.sh` to insert the new steps**

Replace the current body with:

```bash
if [[ "${ENABLE_DSA_SIGNAL_LAYER:-1}" == "1" ]]; then
  if ! run_codex_prompt "dsa_premarket_scan" "$AGENT_ROOT/prompts/signals/dsa_scan.txt"; then
    log_line "dsa_premarket_scan failed; continuing with main premarket research."
  fi
fi

if [[ "${ENABLE_KRONOS_SIGNAL_LAYER:-1}" == "1" ]]; then
  if ! "$SCRIPT_DIR/run_kronos_premarket_scan.sh"; then
    log_line "kronos_premarket_scan failed; continuing with main premarket research."
  fi
fi

if [[ "${ENABLE_MARKET_FEED_LAYER:-1}" == "1" ]]; then
  "$AGENT_ROOT/scripts/data/run_market_feed_collection.sh"
fi

if [[ "${ENABLE_TECHNICAL_SIGNAL_LAYER:-1}" == "1" ]]; then
  "$AGENT_ROOT/scripts/data/run_technical_research.sh"
fi

run_codex_prompt "premarket" "$AGENT_ROOT/prompts/premarket/final_research.txt"
```

- [ ] **Step 4: Update the premarket prompt to consume technical signals**

Add to `prompts/premarket/final_research.txt` under the read list:

```text
- `state/runs/<date>/signals/technical_signals.json` if it exists and is for today
```

Add a new task rule:

```text
Treat `state/runs/<date>/signals/technical_signals.json` as a non-binding but execution-aware research layer:
- `buy_bias` may promote a symbol in ranking but cannot bypass risk, account, or tradability checks.
- `sell_bias` may reduce priority, block adds, or bias an existing long toward trim logic.
- `hold`, `observe`, and `avoid` should suppress executable candidate selection unless current verified evidence is stronger.
- Use `long_setup`, `short_setup`, and `no_trade_zone` to refine the written symbol trade rules in `state/daily_plan.json`.
```

- [ ] **Step 5: Update the intraday prompt to consume key price levels**

Add to the read list in `prompts/intraday/check.txt`:

```text
- `state/runs/<date>/signals/technical_signals.json` if it exists and is for today
```

Add to decision logic:

```text
- Buy candidate only if current price is not inside the symbol's `no_trade_zone`, and either:
  - current price is above `long_setup.trigger_above`, or
  - current price is inside `long_setup.entry_zone`.
- Do not chase above `long_setup.do_not_chase_above`.
- Existing long trim or sell candidate only if `short_setup.status` is `active` or `watch`, and current price is below `short_setup.trigger_below` or otherwise satisfies the plan's partial-take-profit logic.
- Never interpret `short_setup` as permission to open a short position.
```

- [ ] **Step 6: Update the safety checker**

Add to `scripts/safety/check_safety.sh`:

```bash
if [[ -f "$AGENT_ROOT/prompts/technical/research.txt" ]] \
  && rg -q 'state/runs/<date>/signals/technical_signals.json' "$AGENT_ROOT/prompts/premarket/final_research.txt" \
  && rg -q 'state/runs/<date>/signals/technical_signals.json' "$AGENT_ROOT/prompts/intraday/check.txt"; then
  echo "  - Technical signal layer is configured and wired into premarket/intraday: ok"
else
  echo "  - WARNING: technical signal layer is incomplete or not wired into prompts."
fi
```

- [ ] **Step 7: Re-run the wiring tests**

Run: `python3 -m unittest tests/test_technical_signal_schema.py -v`

Expected: PASS for premarket and intraday prompt wiring tests.

- [ ] **Step 8: Commit the workflow integration**

```bash
git add scripts/entrypoints/run_premarket.sh scripts/safety/check_safety.sh prompts/premarket/final_research.txt prompts/intraday/check.txt tests/test_technical_signal_schema.py
git commit -m "feat: wire technical signals into trading workflow"
```

### Task 6: Add the Manual Symbol Research Entry Point

**Files:**
- Create: `scripts/data/run_symbol_research.sh`
- Modify: `tests/test_collect_market_feed.py`

- [ ] **Step 1: Add a failing runner-contract test**

Extend `tests/test_collect_market_feed.py` with:

```python
    def test_run_symbol_research_script_exists(self) -> None:
        self.assertTrue((REPO_ROOT / "scripts" / "run_symbol_research.sh").exists())
```

- [ ] **Step 2: Run the test and verify it fails before the runner exists**

Run: `python3 -m unittest tests/test_collect_market_feed.py -v`

Expected: FAIL on missing `scripts/data/run_symbol_research.sh`.

- [ ] **Step 3: Create the manual symbol runner**

Create `scripts/data/run_symbol_research.sh` with:

```bash
#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 SYMBOL" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

symbol="$(printf '%s' "$1" | tr '[:lower:]' '[:upper:]')"
manual_dir="$AGENT_ROOT/state/market_feed/$(pt_date)-manual-$symbol"
universe_file="$(mktemp "${TMPDIR:-/tmp}/symbol-universe.XXXXXX")"
trap 'rm -f "$universe_file"' EXIT
printf '%s\n' "$symbol" > "$universe_file"

"$MARKET_FEED_PYTHON_BIN" "$AGENT_ROOT/scripts/data/collect_market_feed.py" \
  --universe-file "$universe_file" \
  --output-dir "$manual_dir" \
  --date "$(pt_date)"

MARKET_FEED_DIR="$manual_dir" run_codex_prompt "technical_research" "$AGENT_ROOT/prompts/technical/research.txt"
```

- [ ] **Step 4: Re-run the collector tests**

Run: `python3 -m unittest tests/test_collect_market_feed.py -v`

Expected: PASS for the new script-exists check.

- [ ] **Step 5: Commit the manual research runner**

```bash
git add scripts/data/run_symbol_research.sh tests/test_collect_market_feed.py
git commit -m "feat: add manual symbol research runner"
```

### Task 7: Document Setup and Usage, Then Run Smoke Verification

**Files:**
- Create: `docs/setup/repo-skills.md`
- Create: `docs/setup/market-feed.md`
- Modify: `README.md`

- [ ] **Step 1: Add the repo-skills setup document**

Create `docs/setup/repo-skills.md` with:

````md
# Repo Skills Setup

## Install

```bash
./scripts/skills/install_repo_skills.sh
./scripts/skills/verify_repo_skills.sh
```

## Source of Truth

- Repo source: `.agents/skills/`
- Installed copies:
  - `$HOME/.agents/skills`
  - `~/.codex/skills`

## Notes

- Installs are real copies, not symlinks.
- Re-run the installer after repo skill updates.
```
````

- [ ] **Step 2: Add the market-feed setup document**

Create `docs/setup/market-feed.md` with:

````md
# Market Feed and Technical Research

## Scheduled flow

```bash
./scripts/data/run_market_feed_collection.sh
./scripts/data/run_technical_research.sh
```

## Manual flow

```bash
./scripts/data/run_symbol_research.sh NVDA
```

## Key outputs

- `state/runs/<date>/market_feed/manifest.json`
- `state/runs/<date>/signals/technical_signals.json`

## Testing

```bash
python3 -m unittest tests/test_install_repo_skills.py tests/test_collect_market_feed.py tests/test_technical_signal_schema.py -v
CODEX_EXEC_DRY_RUN=1 ./scripts/entrypoints/run_premarket.sh
```
````

- [ ] **Step 3: Update the main README**

Add a new section to `README.md`:

````md
## Repo-Owned Trading Skills

This repo now ships its own trading skill pack under `.agents/skills/`.

- install: `./scripts/skills/install_repo_skills.sh`
- verify: `./scripts/skills/verify_repo_skills.sh`
- scheduled collector: `./scripts/data/run_market_feed_collection.sh`
- manual symbol research: `./scripts/data/run_symbol_research.sh NVDA`

The premarket workflow now includes:

```text
DSA signal scan
  -> Kronos signal scan
  -> market feed collection
  -> technical research
  -> main premarket planner
```
````

- [ ] **Step 4: Run the full test suite**

Run: `python3 -m unittest tests/test_install_repo_skills.py tests/test_collect_market_feed.py tests/test_technical_signal_schema.py -v`

Expected: PASS for all tests.

- [ ] **Step 5: Run dry-run safety verification**

Run: `./scripts/safety/check_safety.sh`

Expected: includes:
- `Technical signal layer is configured and wired into premarket/intraday: ok`
- `DSA signal layer is configured and wired into premarket/intraday: ok`

- [ ] **Step 6: Run the premarket dry-run smoke path**

Run: `CODEX_EXEC_DRY_RUN=1 ./scripts/entrypoints/run_premarket.sh`

Expected: PASS without calling Codex, and `logs/codex_runs.log` records the scheduled `premarket` path after the collector and technical-research runners complete or log safe skips.

- [ ] **Step 7: Commit the docs and verification updates**

```bash
git add docs/setup/repo-skills.md docs/setup/market-feed.md README.md
git commit -m "docs: add skill feed setup and usage"
```

## Self-Review

- Spec coverage:
  - repo-owned skill pack: Task 1
  - copied installation into both user destinations: Task 1
  - deterministic collector with charts/OHLCV/news: Tasks 2-3
  - dedicated technical-analysis step: Task 4
  - premarket and intraday use of execution-aware price levels: Task 5
  - manual single-symbol flow: Task 6
  - docs and smoke verification: Task 7
- Placeholder scan:
  - no `TODO`, `TBD`, or “implement later” steps remain
  - each test, command, and target file is explicit
- Type consistency:
  - `state/runs/<date>/signals/technical_signals.json` uses `long_setup`, `short_setup`, and `no_trade_zone` consistently
  - `short_setup` remains limited to existing long-position management throughout
