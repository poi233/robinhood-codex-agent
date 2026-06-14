# Policy Engine Intraday Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move intraday trade decision authority from Codex prompts into a deterministic Python policy engine while keeping first-slice review/live execution blocked.

**Architecture:** Add a pure `trading_agent.policy` package for typed inputs, scoring, risk gates, buy/sell intent evaluation, and a single `generate_order_intent()` entrypoint. Update intraday orchestration to load local state, call policy, and append a decision log instead of asking Codex to decide. Add a backtest CLI skeleton that establishes the future policy reuse boundary without implementing full historical simulation yet.

**Tech Stack:** Python 3.11+, dataclasses, argparse, unittest, local JSON state files, existing `trading_agent.core` helpers

---

## File Map

- Create: `trading_agent/policy/__init__.py`
- Create: `trading_agent/policy/models.py`
- Create: `trading_agent/policy/loaders.py`
- Create: `trading_agent/policy/risk.py`
- Create: `trading_agent/policy/scoring.py`
- Create: `trading_agent/policy/buy.py`
- Create: `trading_agent/policy/sell.py`
- Create: `trading_agent/policy/engine.py`
- Create: `trading_agent/backtest/__init__.py`
- Create: `trading_agent/backtest/engine.py`
- Modify: `trading_agent/orchestration/intraday.py`
- Modify: `trading_agent/cli.py`
- Create: `tests/test_policy_engine.py`
- Create: `tests/test_policy_buy_sell.py`
- Create: `tests/test_policy_loaders.py`
- Create: `tests/test_intraday_policy_integration.py`
- Create: `tests/test_backtest_cli.py`

## Responsibility Split

- `models.py`: dataclasses and JSON-safe serialization helpers for policy decisions.
- `loaders.py`: local file loading only; no Codex, no Robinhood, no network.
- `risk.py`: hard fail-closed checks shared by buy/sell/engine.
- `scoring.py`: deterministic candidate score from dynamic allowlist and advisory signals.
- `buy.py`: buy intent rules for long equity/ETF limit orders.
- `sell.py`: sell intent rules for reducing existing long positions only.
- `engine.py`: pure decision priority: global block, sell, buy, no-action.
- `intraday.py`: runtime gates, load inputs, call policy, append one decision record.
- `backtest/engine.py`: first CLI-compatible skeleton for later policy reuse.

### Task 1: Policy Models and Engine Failing Tests

**Files:**
- Create: `tests/test_policy_engine.py`
- Create: `trading_agent/policy/__init__.py`
- Create: `trading_agent/policy/models.py`
- Create: `trading_agent/policy/engine.py`

- [ ] **Step 1: Write failing tests for policy decision shapes**

Create `tests/test_policy_engine.py` with tests that import `PolicyInputs`, `Quote`, `PolicyDecision`, `generate_order_intent`, and verify missing data blocks, review/live execution is unwired, and paper mode can return `would_trade`.

- [ ] **Step 2: Run the tests and verify import failure**

Run: `python3 -m unittest tests/test_policy_engine.py -v`
Expected: FAIL with `No module named 'trading_agent.policy'`.

- [ ] **Step 3: Add policy dataclasses**

Create `trading_agent/policy/models.py` with `Quote`, `Position`, `OpenOrder`, `OrderIntent`, `PolicyInputs`, and `PolicyDecision`. Include `to_json_dict()` methods for `OrderIntent` and `PolicyDecision`.

- [ ] **Step 4: Add minimal engine**

Create `trading_agent/policy/engine.py` with `generate_order_intent(inputs: PolicyInputs) -> PolicyDecision`. Initial behavior blocks missing daily plan, blocks review/live execution when an intent exists, and otherwise returns no-action until buy/sell modules are added.

- [ ] **Step 5: Re-run model tests**

Run: `python3 -m unittest tests/test_policy_engine.py -v`
Expected: PASS.

### Task 2: Risk Gates and Buy/Sell Evaluation

**Files:**
- Create: `tests/test_policy_buy_sell.py`
- Create: `trading_agent/policy/risk.py`
- Create: `trading_agent/policy/scoring.py`
- Create: `trading_agent/policy/buy.py`
- Create: `trading_agent/policy/sell.py`
- Modify: `trading_agent/policy/engine.py`

- [ ] **Step 1: Write failing buy/sell tests**

Create `tests/test_policy_buy_sell.py` covering score threshold, allowlist intersection, missing quote, daily cap exhausted, losing position average-down block, partial take-profit sell, sell quantity not exceeding holdings, and `short_setup` never opening a short.

- [ ] **Step 2: Run tests and verify failures**

Run: `python3 -m unittest tests/test_policy_buy_sell.py -v`
Expected: FAIL because `buy.py`, `sell.py`, `risk.py`, and `scoring.py` do not exist.

- [ ] **Step 3: Implement risk gates**

Create `risk.py` with pure helpers for stale/missing plan, symbol intersection, quote presence, open order block, notional caps, losing-position block, and first-slice execution block.

- [ ] **Step 4: Implement scoring**

Create `scoring.py` with `score_symbol(inputs, symbol) -> int`, starting from `dynamic_allowlist["symbol_scores"][symbol]["score"]` and applying advisory demotions for DSA block and research risk flags.

- [ ] **Step 5: Implement buy and sell evaluation**

Create `buy.py` with `evaluate_buy(inputs) -> OrderIntent | None` and `sell.py` with `evaluate_sell(inputs) -> OrderIntent | None`.

- [ ] **Step 6: Wire engine to sell before buy**

Update `engine.py` so global blocks run first, sell candidates are evaluated before buy candidates, and paper/review/live decision labels are assigned after intent generation.

- [ ] **Step 7: Re-run policy tests**

Run: `python3 -m unittest tests/test_policy_engine.py tests/test_policy_buy_sell.py -v`
Expected: PASS.

### Task 3: Local Policy Loaders

**Files:**
- Create: `tests/test_policy_loaders.py`
- Create: `trading_agent/policy/loaders.py`

- [ ] **Step 1: Write failing loader tests**

Create `tests/test_policy_loaders.py` with a temporary repo containing config/state files. Verify `load_policy_inputs()` reads universe, daily plan, dynamic allowlist, today allowlist, risk tier caps, daily usage, and research report JSON.

- [ ] **Step 2: Run loader tests and verify import failure**

Run: `python3 -m unittest tests/test_policy_loaders.py -v`
Expected: FAIL because `trading_agent.policy.loaders` does not exist.

- [ ] **Step 3: Implement loader**

Create `loaders.py` with `load_policy_inputs(agent_root: Path, run_date: str, trading_mode: str, risk_tier: int) -> PolicyInputs`. Missing optional signal files should load as empty dictionaries; missing required daily plan or allowlist should be represented in `PolicyInputs` so the engine can block.

- [ ] **Step 4: Re-run loader tests**

Run: `python3 -m unittest tests/test_policy_loaders.py -v`
Expected: PASS.

### Task 4: Intraday Policy Integration

**Files:**
- Create: `tests/test_intraday_policy_integration.py`
- Modify: `trading_agent/orchestration/intraday.py`

- [ ] **Step 1: Write failing intraday tests**

Create `tests/test_intraday_policy_integration.py` verifying intraday uses `generate_order_intent`, appends exactly one JSONL decision, does not call `run_codex_prompt`, keeps calendar/time/KILL_SWITCH skips, and blocks review/live with `execution_not_wired`.

- [ ] **Step 2: Run intraday tests and verify failure**

Run: `python3 -m unittest tests/test_intraday_policy_integration.py -v`
Expected: FAIL because intraday still calls Codex prompt.

- [ ] **Step 3: Update intraday orchestration**

Modify `run_intraday_pipeline()` to load runtime config, load policy inputs, call `generate_order_intent()`, and append `decision.to_json_dict()` to `logs/decisions.jsonl`.

- [ ] **Step 4: Re-run intraday tests**

Run: `python3 -m unittest tests/test_intraday_policy_integration.py -v`
Expected: PASS.

### Task 5: Backtest CLI Skeleton

**Files:**
- Create: `tests/test_backtest_cli.py`
- Create: `trading_agent/backtest/__init__.py`
- Create: `trading_agent/backtest/engine.py`
- Modify: `trading_agent/cli.py`
- Modify: `tests/test_package_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_backtest_cli.py` asserting `python3 -m trading_agent backtest --strategy policy_v0 --start 2024-01-01 --end 2024-01-31` exits zero and prints a first-slice skeleton message. Update `tests/test_package_cli.py` to expect `backtest` in top-level help.

- [ ] **Step 2: Run CLI tests and verify failure**

Run: `python3 -m unittest tests/test_backtest_cli.py tests/test_package_cli.py -v`
Expected: FAIL because `backtest` command does not exist.

- [ ] **Step 3: Add backtest skeleton**

Create `trading_agent/backtest/engine.py` with `run_backtest_skeleton()` returning a stable message and no broker access. Update `cli.py` to add `backtest` parser args.

- [ ] **Step 4: Re-run CLI tests**

Run: `python3 -m unittest tests/test_backtest_cli.py tests/test_package_cli.py -v`
Expected: PASS.

### Task 6: Full Verification

**Files:**
- All changed files

- [ ] **Step 1: Run full unit suite**

Run: `python3 -m unittest discover -v`
Expected: PASS.

- [ ] **Step 2: Run package help smoke checks**

Run:

```bash
python3 -m trading_agent --help
python3 -m trading_agent intraday --help
python3 -m trading_agent backtest --help
```

Expected: All exit zero.

- [ ] **Step 3: Inspect git diff**

Run: `git diff --stat` and `git diff -- trading_agent tests docs/superpowers/plans/2026-06-14-policy-engine-intraday-migration.md`.
Expected: Only policy, intraday, CLI, backtest skeleton, tests, and this plan changed. Existing unrelated edits in `config/runtime.env` and `trading_agent/prompts/codex.py` remain untouched.
