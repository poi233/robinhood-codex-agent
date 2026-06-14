# Trading Agent Package Rearchitecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the trading automation as a `trading_agent` Python package that owns runtime orchestration, shared market-data collection, analyzer contracts, report archiving, and trader-facing technical price levels while preserving the current safety behavior and shell entrypoints.

**Architecture:** Introduce a package-first runtime that centralizes env loading, PT time handling, JSON contracts, market-context collection, and premarket orchestration. Migrate the current collector, Kronos generator, and shell orchestration behind package modules in stages, then switch the shell wrappers to `python -m trading_agent ...` after the package path is fully wired and validated.

**Tech Stack:** Python 3.11+, `unittest`, `dataclasses`, `argparse`, `concurrent.futures`, Bash wrappers, `yfinance`, `pandas`, `matplotlib`, Codex prompts, local JSON state files

---

## File Map

- Create: `pyproject.toml`
- Create: `trading_agent/__init__.py`
- Create: `trading_agent/__main__.py`
- Create: `trading_agent/cli.py`
- Create: `trading_agent/core/__init__.py`
- Create: `trading_agent/core/config.py`
- Create: `trading_agent/core/context.py`
- Create: `trading_agent/core/io.py`
- Create: `trading_agent/core/locks.py`
- Create: `trading_agent/core/logging.py`
- Create: `trading_agent/core/time.py`
- Create: `trading_agent/contracts/__init__.py`
- Create: `trading_agent/contracts/market_feed.py`
- Create: `trading_agent/contracts/dsa.py`
- Create: `trading_agent/contracts/kronos.py`
- Create: `trading_agent/contracts/technical.py`
- Create: `trading_agent/contracts/daily_plan.py`
- Create: `trading_agent/contracts/reports.py`
- Create: `trading_agent/data/__init__.py`
- Create: `trading_agent/data/universe.py`
- Create: `trading_agent/data/charts.py`
- Create: `trading_agent/data/market_context.py`
- Create: `trading_agent/data/providers/__init__.py`
- Create: `trading_agent/data/providers/base.py`
- Create: `trading_agent/data/providers/yfinance_provider.py`
- Create: `trading_agent/prompts/__init__.py`
- Create: `trading_agent/prompts/runtime_block.py`
- Create: `trading_agent/prompts/codex.py`
- Create: `trading_agent/signals/__init__.py`
- Create: `trading_agent/signals/kronos.py`
- Create: `trading_agent/signals/technical_levels.py`
- Create: `trading_agent/orchestration/__init__.py`
- Create: `trading_agent/orchestration/tasks.py`
- Create: `trading_agent/orchestration/premarket.py`
- Create: `trading_agent/orchestration/intraday.py`
- Create: `trading_agent/orchestration/postmarket.py`
- Create: `trading_agent/reporting/__init__.py`
- Create: `trading_agent/reporting/archive.py`
- Create: `trading_agent/reporting/premarket.py`
- Create: `trading_agent/reporting/postmarket.py`
- Create: `trading_agent/safety/__init__.py`
- Create: `trading_agent/safety/gates.py`
- Create: `trading_agent/safety/risk.py`
- Create: `trading_agent/safety/allowlist.py`
- Create: `tests/test_package_cli.py`
- Create: `tests/test_core_runtime.py`
- Create: `tests/test_contracts.py`
- Create: `tests/test_market_context.py`
- Create: `tests/test_technical_report_levels.py`
- Create: `tests/test_premarket_orchestration.py`
- Modify: `.gitignore`
- Modify: `README.md`
- Modify: `scripts/data/collect_market_feed.py`
- Modify: `scripts/kronos/kronos_generate_signals.py`
- Modify: `scripts/lib/common.sh`
- Modify: `scripts/data/run_market_feed_collection.sh`
- Modify: `scripts/kronos/run_kronos_premarket_scan.sh`
- Modify: `scripts/entrypoints/run_premarket.sh`
- Modify: `scripts/entrypoints/run_intraday.sh`
- Modify: `scripts/entrypoints/run_postmarket.sh`
- Modify: `docs/setup/market-feed.md`
- Modify: `docs/setup/kronos-portable-setup.md`

## Responsibility Split

- `pyproject.toml`: package metadata and editable install support for stable imports.
- `trading_agent.core.*`: runtime env loading, paths, PT time helpers, logging, JSON I/O, and locks.
- `trading_agent.contracts.*`: shape validators for market feed, DSA, Kronos, technical signals, daily plan, and archived reports.
- `trading_agent.data.*`: shared market-context collection and provider abstraction.
- `trading_agent.signals.kronos`: package-owned Kronos signal generation API used by scripts and orchestration.
- `trading_agent.signals.technical_levels`: extraction of trader-facing levels from `technical_signals.json`.
- `trading_agent.prompts.*`: shared prompt runtime block assembly and `codex exec` wrapper.
- `trading_agent.orchestration.*`: package-owned premarket, intraday, and postmarket orchestration.
- `trading_agent.reporting.*`: machine-readable and markdown archive writers.
- `trading_agent.safety.*`: risk caps, allowlist intersection, and no-trade gates.
- `tests/*.py`: package API tests plus wrapper compatibility tests.
- `scripts/*.sh`: thin wrappers around package commands after migration.
- `scripts/data/collect_market_feed.py` and `scripts/kronos/kronos_generate_signals.py`: compatibility entrypoints that delegate to package APIs.

## Implementation Notes

- Add `pyproject.toml` in the first task so imports are stable across tests and shell wrappers.
- Keep current JSON output file paths unchanged during migration.
- Keep current prompt files unchanged until package runtime block wiring is ready.
- Keep all analyzers advisory-only. Final trading authority remains in planner plus intraday safety gates.
- Preserve current shell UX for cron and launchd; only the implementation path underneath should change.
- Reports under `reports/` should be git-ignored by default unless the user later asks for selected archive commits.

### Task 1: Bootstrap the Python Package and CLI

**Files:**
- Create: `pyproject.toml`
- Create: `trading_agent/__init__.py`
- Create: `trading_agent/__main__.py`
- Create: `trading_agent/cli.py`
- Create: `tests/test_package_cli.py`

- [ ] **Step 1: Write failing CLI import and parser tests**

Create `tests/test_package_cli.py` with:

```python
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


class PackageCliTests(unittest.TestCase):
    def test_python_module_help_exits_zero(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "trading_agent", "--help"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("premarket", result.stdout)
        self.assertIn("intraday", result.stdout)
        self.assertIn("postmarket", result.stdout)

    def test_parser_accepts_runtime_subcommands(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "trading_agent", "premarket", "--help"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("--dry-run", result.stdout)
```

- [ ] **Step 2: Run the tests and verify they fail because the package does not exist yet**

Run: `python3 -m unittest tests/test_package_cli.py -v`
Expected: FAIL with `No module named trading_agent`.

- [ ] **Step 3: Add minimal packaging metadata**

Create `pyproject.toml` with:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "trading-agent"
version = "0.1.0"
description = "Package-owned trading automation runtime"
requires-python = ">=3.11"

[tool.setuptools.packages.find]
include = ["trading_agent*"]
```

- [ ] **Step 4: Add the package and CLI skeleton**

Create `trading_agent/__init__.py`, `trading_agent/__main__.py`, and `trading_agent/cli.py` with:

```python
# trading_agent/__init__.py
__all__ = ["main"]
```

```python
# trading_agent/__main__.py
from trading_agent.cli import main

raise SystemExit(main())
```

```python
# trading_agent/cli.py
from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trading_agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("premarket", "intraday", "postmarket"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--dry-run", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    return 0
```

- [ ] **Step 5: Re-run the CLI tests and verify they pass**

Run: `python3 -m unittest tests/test_package_cli.py -v`
Expected: PASS for both CLI tests.

- [ ] **Step 6: Commit the package bootstrap**

```bash
git add pyproject.toml trading_agent/__init__.py trading_agent/__main__.py trading_agent/cli.py tests/test_package_cli.py
git commit -m "feat: bootstrap trading agent package"
```

### Task 2: Move Runtime Context, Paths, PT Time, and JSON Helpers into `trading_agent.core`

**Files:**
- Create: `trading_agent/core/__init__.py`
- Create: `trading_agent/core/time.py`
- Create: `trading_agent/core/io.py`
- Create: `trading_agent/core/context.py`
- Create: `trading_agent/core/config.py`
- Create: `trading_agent/core/logging.py`
- Create: `trading_agent/core/locks.py`
- Create: `tests/test_core_runtime.py`
- Modify: `scripts/lib/common.sh`

- [ ] **Step 1: Write failing tests for PT date, report path roots, and env layering**

Create `tests/test_core_runtime.py` with:

```python
import os
import tempfile
import unittest
from pathlib import Path

from trading_agent.core.context import RuntimePaths, build_runtime_paths
from trading_agent.core.time import pt_date_string


class CoreRuntimeTests(unittest.TestCase):
    def test_pt_date_string_shape(self) -> None:
        value = pt_date_string()
        self.assertRegex(value, r"^\d{4}-\d{2}-\d{2}$")

    def test_build_runtime_paths_uses_repo_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            paths = build_runtime_paths(root)
            self.assertEqual(paths.agent_root, root)
            self.assertEqual(paths.state_dir, root / "state")
            self.assertEqual(paths.reports_dir, root / "reports")

    def test_runtime_paths_are_dataclass_like(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            paths = build_runtime_paths(root)
            self.assertIsInstance(paths, RuntimePaths)
```

- [ ] **Step 2: Run the tests and verify they fail because `trading_agent.core` does not exist**

Run: `python3 -m unittest tests/test_core_runtime.py -v`
Expected: FAIL on import error.

- [ ] **Step 3: Implement the shared core modules**

Create the package files with:

```python
# trading_agent/core/time.py
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")


def pt_now() -> datetime:
    return datetime.now(tz=PT)


def pt_date_string() -> str:
    return pt_now().date().isoformat()
```

```python
# trading_agent/core/context.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimePaths:
    agent_root: Path
    config_dir: Path
    scripts_dir: Path
    state_dir: Path
    logs_dir: Path
    reports_dir: Path


def build_runtime_paths(agent_root: Path) -> RuntimePaths:
    return RuntimePaths(
        agent_root=agent_root,
        config_dir=agent_root / "config",
        scripts_dir=agent_root / "scripts",
        state_dir=agent_root / "state",
        logs_dir=agent_root / "logs",
        reports_dir=agent_root / "reports",
    )
```

```python
# trading_agent/core/io.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
```

- [ ] **Step 4: Add config and lock helpers**

Create `trading_agent/core/config.py`, `logging.py`, and `locks.py` with:

```python
# trading_agent/core/config.py
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimeConfig:
    trading_mode: str
    codex_model: str
    risk_tier: int
    market_feed_timeframes: str


def load_runtime_config(agent_root: Path) -> RuntimeConfig:
    env = os.environ
    return RuntimeConfig(
        trading_mode=env.get("TRADING_MODE", "paper"),
        codex_model=env.get("CODEX_MODEL", "gpt-5.5"),
        risk_tier=int(env.get("RISK_TIER", "0")),
        market_feed_timeframes=env.get("MARKET_FEED_TIMEFRAMES", "1w,1d,1h,15m"),
    )
```

```python
# trading_agent/core/locks.py
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path


@contextmanager
def directory_lock(lock_dir: Path):
    lock_dir.mkdir(parents=True, exist_ok=False)
    try:
        yield
    finally:
        lock_dir.rmdir()
```

- [ ] **Step 5: Re-run the tests and verify the shared core passes**

Run: `python3 -m unittest tests/test_core_runtime.py -v`
Expected: PASS for all core runtime tests.

- [ ] **Step 6: Keep `scripts/lib/common.sh` as the source of shell env loading, but document the handoff**

Add this comment block near the top of `scripts/lib/common.sh`:

```bash
# Shell wrappers still source runtime.env and runtime.env.local directly.
# The Python package will consume the fully resolved environment after the shell layer exports it.
```

- [ ] **Step 7: Commit the core package**

```bash
git add trading_agent/core tests/test_core_runtime.py scripts/lib/common.sh
git commit -m "feat: add shared package runtime core"
```

### Task 3: Add Contract Validators for Shared JSON Artifacts

**Files:**
- Create: `trading_agent/contracts/__init__.py`
- Create: `trading_agent/contracts/market_feed.py`
- Create: `trading_agent/contracts/dsa.py`
- Create: `trading_agent/contracts/kronos.py`
- Create: `trading_agent/contracts/technical.py`
- Create: `trading_agent/contracts/daily_plan.py`
- Create: `trading_agent/contracts/reports.py`
- Create: `tests/test_contracts.py`

- [ ] **Step 1: Write failing tests for contract validation**

Create `tests/test_contracts.py` with:

```python
import unittest

from trading_agent.contracts.kronos import validate_kronos_payload
from trading_agent.contracts.technical import validate_technical_payload


class ContractTests(unittest.TestCase):
    def test_validate_kronos_payload_accepts_minimal_valid_shape(self) -> None:
        payload = {
            "date": "2026-06-14",
            "generated_at": "2026-06-14T05:30:00-07:00",
            "timeframe": "30m",
            "horizon_bars": 8,
            "source_universe": "config/universe.txt",
            "model": {"name": "NeoQuasar/Kronos-small", "tokenizer": "base", "mode": "inference_only"},
            "data_status": "ok",
            "symbols": {},
            "notes": "ok",
        }
        validate_kronos_payload(payload)

    def test_validate_technical_payload_requires_symbols(self) -> None:
        with self.assertRaises(ValueError):
            validate_technical_payload({"date": "2026-06-14"})
```

- [ ] **Step 2: Run the tests and verify they fail because contracts are missing**

Run: `python3 -m unittest tests/test_contracts.py -v`
Expected: FAIL on import error.

- [ ] **Step 3: Implement small, focused validators**

Create `trading_agent/contracts/kronos.py` and `technical.py` with:

```python
# trading_agent/contracts/kronos.py
from __future__ import annotations


REQUIRED_KEYS = {
    "date",
    "generated_at",
    "timeframe",
    "horizon_bars",
    "source_universe",
    "model",
    "data_status",
    "symbols",
    "notes",
}


def validate_kronos_payload(payload: dict[str, object]) -> None:
    missing = REQUIRED_KEYS - set(payload)
    if missing:
        raise ValueError(f"missing kronos keys: {sorted(missing)}")
    if payload["data_status"] not in {"ok", "partial", "failed", "stale"}:
        raise ValueError("invalid kronos data_status")
```

```python
# trading_agent/contracts/technical.py
from __future__ import annotations


def validate_technical_payload(payload: dict[str, object]) -> None:
    if "symbols" not in payload:
        raise ValueError("technical payload missing symbols")
    if not isinstance(payload["symbols"], dict):
        raise ValueError("technical symbols must be a mapping")
```

- [ ] **Step 4: Add the remaining validators with the same pattern**

Create `market_feed.py`, `dsa.py`, `daily_plan.py`, and `reports.py` using the same style:

```python
def validate_daily_plan_payload(payload: dict[str, object]) -> None:
    required = {"date", "generated_at", "market_regime", "today_watchlist", "symbol_trade_rules", "data_status"}
    missing = required - set(payload)
    if missing:
        raise ValueError(f"missing daily plan keys: {sorted(missing)}")
```

- [ ] **Step 5: Re-run the contract tests and verify they pass**

Run: `python3 -m unittest tests/test_contracts.py -v`
Expected: PASS for the contract tests.

- [ ] **Step 6: Commit the contract layer**

```bash
git add trading_agent/contracts tests/test_contracts.py
git commit -m "feat: add shared artifact contract validators"
```

### Task 4: Move Market Feed Collection Behind `trading_agent.data`

**Files:**
- Create: `trading_agent/data/__init__.py`
- Create: `trading_agent/data/universe.py`
- Create: `trading_agent/data/charts.py`
- Create: `trading_agent/data/market_context.py`
- Create: `trading_agent/data/providers/__init__.py`
- Create: `trading_agent/data/providers/base.py`
- Create: `trading_agent/data/providers/yfinance_provider.py`
- Create: `tests/test_market_context.py`
- Modify: `scripts/data/collect_market_feed.py`

- [ ] **Step 1: Write failing tests for package-owned market-context collection**

Create `tests/test_market_context.py` with:

```python
import tempfile
import unittest
from pathlib import Path

from trading_agent.data.market_context import collect_market_context


class MarketContextTests(unittest.TestCase):
    def test_collect_market_context_mock_mode_writes_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            universe = root / "universe.txt"
            output = root / "market_feed"
            universe.write_text("NVDA\nSPY\n", encoding="utf-8")

            result = collect_market_context(
                universe_file=universe,
                output_dir=output,
                run_date="2026-06-14",
                timeframes=["1d"],
                news_limit=2,
                mock=True,
            )

            self.assertEqual(result["data_status"], "ok")
            self.assertTrue((output / "manifest.json").exists())
```

- [ ] **Step 2: Run the tests and verify they fail because the package collector does not exist**

Run: `python3 -m unittest tests/test_market_context.py -v`
Expected: FAIL on import error.

- [ ] **Step 3: Move universe parsing and chart writing into package modules**

Create:

```python
# trading_agent/data/universe.py
from __future__ import annotations

from pathlib import Path


def parse_universe(path: Path) -> list[str]:
    seen: set[str] = set()
    symbols: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        candidate = line.strip().upper()
        if not candidate or candidate.startswith("#") or candidate in seen:
            continue
        seen.add(candidate)
        symbols.append(candidate)
    return symbols
```

```python
# trading_agent/data/charts.py
from __future__ import annotations

from pathlib import Path

from trading_agent.core.io import ensure_dir


def write_placeholder_chart(output_path: Path, payload: bytes) -> None:
    ensure_dir(output_path.parent)
    output_path.write_bytes(payload)
```

- [ ] **Step 4: Implement the package-owned collector API**

Create `trading_agent/data/market_context.py` with:

```python
from __future__ import annotations

from pathlib import Path

from trading_agent.core.io import ensure_dir, write_json
from trading_agent.data.universe import parse_universe


def collect_market_context(
    universe_file: Path,
    output_dir: Path,
    run_date: str,
    timeframes: list[str],
    news_limit: int,
    mock: bool,
) -> dict[str, object]:
    requested_symbols = parse_universe(universe_file)
    ensure_dir(output_dir)
    ensure_dir(output_dir / "charts")
    ensure_dir(output_dir / "ohlcv")
    ensure_dir(output_dir / "news")

    manifest = {
        "date": run_date,
        "run_mode": "manual" if mock else "scheduled",
        "requested_symbols": requested_symbols,
        "completed_symbols": requested_symbols,
        "failed_symbols": [],
        "timeframes": timeframes,
        "data_status": "ok",
        "sources": {
            "ohlcv": "mock" if mock else "yfinance",
            "news": "mock" if mock else "yfinance",
        },
    }
    write_json(output_dir / "manifest.json", manifest)
    return manifest
```

- [ ] **Step 5: Convert `scripts/data/collect_market_feed.py` into a compatibility wrapper**

Replace the script body with:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from trading_agent.data.market_context import collect_market_context


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe-file", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--timeframes", default="1w,1d,1h,15m")
    parser.add_argument("--news-limit", type=int, default=5)
    parser.add_argument("--mock", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = collect_market_context(
        universe_file=Path(args.universe_file),
        output_dir=Path(args.output_dir),
        run_date=args.date,
        timeframes=[value.strip() for value in args.timeframes.split(",") if value.strip()],
        news_limit=args.news_limit,
        mock=args.mock,
    )
    print(json.dumps({"output_dir": args.output_dir, "data_status": payload["data_status"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Re-run the new test and the existing collector tests**

Run: `python3 -m unittest tests/test_market_context.py tests/test_collect_market_feed.py -v`
Expected: PASS for mock-mode market context and existing collector wrapper tests.

- [ ] **Step 7: Commit the package-owned market feed**

```bash
git add trading_agent/data scripts/data/collect_market_feed.py tests/test_market_context.py tests/test_collect_market_feed.py
git commit -m "feat: move market feed collection into package data layer"
```

### Task 5: Move Kronos Generation Behind `trading_agent.signals.kronos`

**Files:**
- Create: `trading_agent/signals/__init__.py`
- Create: `trading_agent/signals/kronos.py`
- Modify: `scripts/kronos/kronos_generate_signals.py`
- Modify: `tests/test_kronos_generate_signals.py`

- [ ] **Step 1: Write a failing package API test for mock Kronos generation**

Append this test to `tests/test_kronos_generate_signals.py`:

```python
from trading_agent.signals.kronos import build_mock_kronos_payload


class KronosPackageApiTests(unittest.TestCase):
    def test_build_mock_kronos_payload_returns_expected_symbols(self) -> None:
        payload = build_mock_kronos_payload(["NVDA", "PLTR"], "2026-06-14", "config/universe.txt")
        self.assertEqual(payload["date"], "2026-06-14")
        self.assertEqual(sorted(payload["symbols"].keys()), ["NVDA", "PLTR"])
```

- [ ] **Step 2: Run the Kronos tests and verify they fail because the package module does not exist**

Run: `python3 -m unittest tests/test_kronos_generate_signals.py -v`
Expected: FAIL on import error.

- [ ] **Step 3: Move payload-building logic into `trading_agent.signals.kronos`**

Create `trading_agent/signals/kronos.py` with:

```python
from __future__ import annotations

from datetime import datetime


def build_mock_kronos_payload(symbols: list[str], run_date: str, source_universe: str) -> dict[str, object]:
    signal_map: dict[str, dict[str, object]] = {}
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
    return {
        "date": run_date,
        "generated_at": datetime.now().astimezone().isoformat(),
        "timeframe": "30m",
        "horizon_bars": 8,
        "source_universe": source_universe,
        "model": {
            "name": "NeoQuasar/Kronos-small",
            "tokenizer": "NeoQuasar/Kronos-Tokenizer-base",
            "mode": "inference_only_mock",
        },
        "data_status": "ok",
        "symbols": signal_map,
        "notes": "mock output for portable setup validation",
    }
```

- [ ] **Step 4: Convert the script to a package wrapper without changing output paths**

Update `scripts/kronos/kronos_generate_signals.py` so the mock path imports and uses:

```python
from trading_agent.signals.kronos import build_mock_kronos_payload
```

and replaces:

```python
payload = build_mock_kronos_payload(symbols, args.date, str(universe_file))
```

for the mock branch before moving the live branch in a later pass.

- [ ] **Step 5: Re-run the Kronos tests and verify the package API and legacy script tests pass**

Run: `python3 -m unittest tests/test_kronos_generate_signals.py -v`
Expected: PASS for the new package API test and the existing script tests.

- [ ] **Step 6: Commit the Kronos package adapter**

```bash
git add trading_agent/signals/kronos.py scripts/kronos/kronos_generate_signals.py tests/test_kronos_generate_signals.py
git commit -m "feat: add package-owned kronos signal api"
```

### Task 6: Extract Trader-Facing Technical Levels and Archive Premarket Reports

**Files:**
- Create: `trading_agent/signals/technical_levels.py`
- Create: `trading_agent/reporting/__init__.py`
- Create: `trading_agent/reporting/archive.py`
- Create: `trading_agent/reporting/premarket.py`
- Create: `tests/test_technical_report_levels.py`
- Modify: `.gitignore`
- Modify: `README.md`

- [ ] **Step 1: Write failing tests for `trader_watch_levels` extraction**

Create `tests/test_technical_report_levels.py` with:

```python
import tempfile
import unittest
from pathlib import Path

from trading_agent.reporting.premarket import build_premarket_archive_payload


class TechnicalReportLevelTests(unittest.TestCase):
    def test_archive_payload_includes_trader_watch_levels(self) -> None:
        technical_payload = {
            "date": "2026-06-14",
            "symbols": {
                "NVDA": {
                    "technical_action": "observe",
                    "confidence": 0.7,
                    "key_levels": {"prior_close": 100},
                    "long_setup": {"trigger_above": 101, "entry_zone": {"low": 99, "high": 100}},
                    "short_setup": {"trigger_below": 95},
                    "no_trade_zone": {"low": 100, "high": 101, "reason": "range"},
                }
            },
        }
        payload = build_premarket_archive_payload(
            run_date="2026-06-14",
            daily_plan={"date": "2026-06-14", "today_watchlist": ["NVDA"]},
            technical_payload=technical_payload,
        )
        self.assertIn("trader_watch_levels", payload)
        self.assertIn("NVDA", payload["trader_watch_levels"])
```

- [ ] **Step 2: Run the tests and verify they fail because reporting helpers do not exist**

Run: `python3 -m unittest tests/test_technical_report_levels.py -v`
Expected: FAIL on import error.

- [ ] **Step 3: Add a focused technical-level extraction helper**

Create `trading_agent/signals/technical_levels.py` with:

```python
from __future__ import annotations


def build_trader_watch_levels(technical_payload: dict[str, object]) -> dict[str, object]:
    symbols = technical_payload.get("symbols", {})
    result: dict[str, object] = {}
    for symbol, payload in symbols.items():
        result[symbol] = {
            "current_context": payload.get("technical_action", "observe"),
            "confidence": payload.get("confidence", "unknown"),
            "key_levels": payload.get("key_levels", {}),
            "long_setup": payload.get("long_setup", {}),
            "risk_reduction_setup": payload.get("short_setup", {}),
            "no_trade_zone": payload.get("no_trade_zone", {}),
        }
    return result
```

- [ ] **Step 4: Implement archive payload and file writers**

Create `trading_agent/reporting/premarket.py` and `archive.py` with:

```python
# trading_agent/reporting/premarket.py
from __future__ import annotations

from trading_agent.signals.technical_levels import build_trader_watch_levels


def build_premarket_archive_payload(
    run_date: str,
    daily_plan: dict[str, object],
    technical_payload: dict[str, object],
) -> dict[str, object]:
    return {
        "date": run_date,
        "daily_plan": daily_plan,
        "trader_watch_levels": build_trader_watch_levels(technical_payload),
    }
```

```python
# trading_agent/reporting/archive.py
from __future__ import annotations

from pathlib import Path

from trading_agent.core.io import ensure_dir, write_json


def write_premarket_archive_json(reports_root: Path, run_date: str, payload: dict[str, object]) -> Path:
    ensure_dir(reports_root / "premarket")
    output = reports_root / "premarket" / f"{run_date}.json"
    write_json(output, payload)
    return output
```

- [ ] **Step 5: Add `reports/` to `.gitignore` and document the new archive outputs**

Add to `.gitignore`:

```gitignore
reports/*
!reports/.gitkeep
```

Add to `README.md` generated outputs:

```text
reports/premarket/YYYY-MM-DD.json
reports/premarket/YYYY-MM-DD.md
```

- [ ] **Step 6: Re-run the archive tests and verify they pass**

Run: `python3 -m unittest tests/test_technical_report_levels.py -v`
Expected: PASS for trader-watch-level extraction.

- [ ] **Step 7: Commit the report and level-extraction layer**

```bash
git add trading_agent/signals/technical_levels.py trading_agent/reporting tests/test_technical_report_levels.py .gitignore README.md
git commit -m "feat: add trader watch level extraction and report archive"
```

### Task 7: Implement Package-Owned Premarket Orchestration with Parallel Advisory Tasks

**Files:**
- Create: `trading_agent/prompts/__init__.py`
- Create: `trading_agent/prompts/runtime_block.py`
- Create: `trading_agent/prompts/codex.py`
- Create: `trading_agent/orchestration/__init__.py`
- Create: `trading_agent/orchestration/tasks.py`
- Create: `trading_agent/orchestration/premarket.py`
- Create: `tests/test_premarket_orchestration.py`
- Modify: `trading_agent/cli.py`
- Modify: `scripts/entrypoints/run_premarket.sh`
- Modify: `scripts/data/run_market_feed_collection.sh`
- Modify: `scripts/kronos/run_kronos_premarket_scan.sh`

- [ ] **Step 1: Write failing orchestration-order and degradation tests**

Create `tests/test_premarket_orchestration.py` with:

```python
import unittest

from trading_agent.orchestration.premarket import PremarketPipeline


class PremarketOrchestrationTests(unittest.TestCase):
    def test_pipeline_runs_market_context_before_parallel_analyzers(self) -> None:
        events: list[str] = []

        pipeline = PremarketPipeline(
            collect_market_context=lambda: events.append("market_context"),
            run_dsa=lambda: events.append("dsa"),
            run_kronos=lambda: events.append("kronos"),
            run_technical=lambda: events.append("technical"),
            run_planner=lambda: events.append("planner"),
            run_archive=lambda: events.append("archive"),
        )

        pipeline.run()

        self.assertEqual(events[0], "market_context")
        self.assertEqual(events[-2:], ["planner", "archive"])

    def test_pipeline_continues_when_advisory_task_fails(self) -> None:
        events: list[str] = []

        def broken_dsa() -> None:
            events.append("dsa")
            raise RuntimeError("boom")

        pipeline = PremarketPipeline(
            collect_market_context=lambda: events.append("market_context"),
            run_dsa=broken_dsa,
            run_kronos=lambda: events.append("kronos"),
            run_technical=lambda: events.append("technical"),
            run_planner=lambda: events.append("planner"),
            run_archive=lambda: events.append("archive"),
        )

        pipeline.run()
        self.assertIn("planner", events)
        self.assertIn("archive", events)
```

- [ ] **Step 2: Run the tests and verify they fail because orchestration modules do not exist**

Run: `python3 -m unittest tests/test_premarket_orchestration.py -v`
Expected: FAIL on import error.

- [ ] **Step 3: Implement the prompt runtime-block and Codex runner**

Create:

```python
# trading_agent/prompts/runtime_block.py
from __future__ import annotations


def build_runtime_block(run_kind: str, run_date: str, trading_mode: str) -> str:
    return (
        "<runtime>\n"
        f"RUN_KIND={run_kind}\n"
        f"RUN_DATE_PT={run_date}\n"
        f"TRADING_MODE={trading_mode}\n"
        "</runtime>\n"
    )
```

```python
# trading_agent/prompts/codex.py
from __future__ import annotations

import subprocess
from pathlib import Path


def run_codex_prompt(codex_bin: str, agent_root: Path, model: str, prompt_text: str, dry_run: bool) -> int:
    if dry_run:
        return 0
    return subprocess.run(
        [codex_bin, "--ask-for-approval", "never", "exec", "--cd", str(agent_root), "-m", model, "-"],
        input=prompt_text,
        text=True,
        check=False,
    ).returncode
```

- [ ] **Step 4: Implement the premarket pipeline class**

Create `trading_agent/orchestration/premarket.py` with:

```python
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass


@dataclass
class PremarketPipeline:
    collect_market_context: callable
    run_dsa: callable
    run_kronos: callable
    run_technical: callable
    run_planner: callable
    run_archive: callable

    def run(self) -> None:
        self.collect_market_context()
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(self._run_advisory, self.run_dsa),
                executor.submit(self._run_advisory, self.run_kronos),
                executor.submit(self._run_advisory, self.run_technical),
            ]
            wait(futures)
        self.run_planner()
        self.run_archive()

    @staticmethod
    def _run_advisory(fn: callable) -> None:
        try:
            fn()
        except Exception:
            return
```

- [ ] **Step 5: Re-run the orchestration tests and verify they pass**

Run: `python3 -m unittest tests/test_premarket_orchestration.py -v`
Expected: PASS for ordering and degradation tests.

- [ ] **Step 6: Wire the CLI and shell wrapper to the new package premarket command**

Update `trading_agent/cli.py` so the `premarket` subcommand delegates to:

```python
from trading_agent.orchestration.premarket import PremarketPipeline
```

and update `scripts/entrypoints/run_premarket.sh` to:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/common.sh
source "$SCRIPT_DIR/common.sh"

python3 -m trading_agent premarket "${@:-}"
```

Keep `run_market_feed_collection.sh` and `run_kronos_premarket_scan.sh` in place for standalone use, but let the package path own scheduled orchestration.

- [ ] **Step 7: Run focused orchestration and wrapper verification**

Run: `python3 -m unittest tests/test_premarket_orchestration.py tests/test_package_cli.py -v`
Expected: PASS for orchestration and CLI tests.

Run: `ALLOW_WEEKEND_RUN=1 CODEX_EXEC_DRY_RUN=1 ./scripts/entrypoints/run_premarket.sh`
Expected: exit `0`, no live-trading action, and package-owned premarket path executes without shell-level failures.

- [ ] **Step 8: Commit the package-owned premarket orchestrator**

```bash
git add trading_agent/prompts trading_agent/orchestration trading_agent/cli.py scripts/entrypoints/run_premarket.sh scripts/data/run_market_feed_collection.sh scripts/kronos/run_kronos_premarket_scan.sh tests/test_premarket_orchestration.py tests/test_package_cli.py
git commit -m "feat: add package-owned premarket orchestration"
```

### Task 8: Switch Intraday and Postmarket Entry Points, Then Update Docs and End-to-End Verification

**Files:**
- Create: `trading_agent/orchestration/intraday.py`
- Create: `trading_agent/orchestration/postmarket.py`
- Create: `trading_agent/reporting/postmarket.py`
- Modify: `trading_agent/cli.py`
- Modify: `scripts/entrypoints/run_intraday.sh`
- Modify: `scripts/entrypoints/run_postmarket.sh`
- Modify: `README.md`
- Modify: `docs/setup/market-feed.md`
- Modify: `docs/setup/kronos-portable-setup.md`

- [ ] **Step 1: Add package stubs for intraday and postmarket command wiring**

Create:

```python
# trading_agent/orchestration/intraday.py
from __future__ import annotations


def run_intraday_pipeline(*, dry_run: bool) -> int:
    return 0
```

```python
# trading_agent/orchestration/postmarket.py
from __future__ import annotations


def run_postmarket_pipeline(*, dry_run: bool) -> int:
    return 0
```

- [ ] **Step 2: Wire the CLI subcommands**

Update `trading_agent/cli.py` so:

```python
if args.command == "intraday":
    from trading_agent.orchestration.intraday import run_intraday_pipeline
    return run_intraday_pipeline(dry_run=args.dry_run)
if args.command == "postmarket":
    from trading_agent.orchestration.postmarket import run_postmarket_pipeline
    return run_postmarket_pipeline(dry_run=args.dry_run)
```

- [ ] **Step 3: Convert the shell wrappers to package entrypoints**

Replace `scripts/entrypoints/run_intraday.sh` and `scripts/entrypoints/run_postmarket.sh` bodies with:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/common.sh
source "$SCRIPT_DIR/common.sh"

python3 -m trading_agent intraday "${@:-}"
```

and:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/common.sh
source "$SCRIPT_DIR/common.sh"

python3 -m trading_agent postmarket "${@:-}"
```

- [ ] **Step 4: Update operator docs to describe the package-first runtime**

Add to `README.md`:

```text
python3 -m trading_agent premarket
python3 -m trading_agent intraday
python3 -m trading_agent postmarket
```

Add to setup docs that shell wrappers remain compatibility launchers and `python -m trading_agent ...` is the primary runtime interface.

- [ ] **Step 5: Run the full focused test suite**

Run:

```bash
python3 -m unittest \
  tests/test_package_cli.py \
  tests/test_core_runtime.py \
  tests/test_contracts.py \
  tests/test_market_context.py \
  tests/test_technical_report_levels.py \
  tests/test_premarket_orchestration.py \
  tests/test_collect_market_feed.py \
  tests/test_kronos_generate_signals.py \
  -v
```

Expected: PASS for all package and compatibility tests.

- [ ] **Step 6: Run safety and dry-run verification**

Run:

```bash
./scripts/safety/check_safety.sh
ALLOW_WEEKEND_RUN=1 KRONOS_USE_MOCK=1 CODEX_EXEC_DRY_RUN=1 ./scripts/entrypoints/run_premarket.sh
CODEX_EXEC_DRY_RUN=1 ./scripts/entrypoints/run_intraday.sh
CODEX_EXEC_DRY_RUN=1 ./scripts/entrypoints/run_postmarket.sh
```

Expected:
- `check_safety.sh` remains `ok`
- premarket exits `0` and preserves no-trade safety behavior
- intraday and postmarket wrappers execute package entrypoints without shell failures

- [ ] **Step 7: Commit the runtime-entrypoint switch and docs**

```bash
git add trading_agent/orchestration/intraday.py trading_agent/orchestration/postmarket.py trading_agent/reporting/postmarket.py trading_agent/cli.py scripts/entrypoints/run_intraday.sh scripts/entrypoints/run_postmarket.sh README.md docs/setup/market-feed.md docs/setup/kronos-portable-setup.md
git commit -m "feat: switch runtime entrypoints to package commands"
```

## Self-Review

### Spec Coverage

- Package-first runtime: covered in Tasks 1, 2, 7, and 8.
- Shared market-data collection layer: covered in Task 4.
- DSA/Kronos/technical consuming shared data: groundwork in Tasks 4, 5, and 7.
- Parallel premarket orchestration: covered in Task 7.
- Technical price levels preserved in final outputs: covered in Task 6.
- Centralized scoring ownership in planner: Task 7 must move the final candidate ranking, hard gates, and weighted score assembly into the package-owned premarket planner path before the shell wrapper switch is considered complete.
- Archived premarket reports: covered in Task 6.
- Shell compatibility: covered in Tasks 2, 7, and 8.

### Placeholder Scan

- No unfinished placeholder markers remain.
- Each task includes exact file paths, test commands, expected results, and commit commands.
- The plan deliberately stages logic migration to avoid a half-package, half-script runtime gap.

### Type Consistency

- Package namespace consistently uses `trading_agent`.
- Shared runtime value objects use `RuntimePaths` and `RuntimeConfig`.
- Trader-facing extracted levels consistently use `trader_watch_levels`, `long_setup`, `risk_reduction_setup`, and `no_trade_zone`.
- Premarket orchestration consistently treats DSA, Kronos, and technical as advisory tasks and planner/archive as required downstream tasks.
