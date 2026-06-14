# Premarket E2E Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the real-data premarket pipeline faster, clearer, and safer for paper trading while preserving full test coverage on closed-market days.

**Architecture:** Keep the existing `src/` package layout and daily run-folder outputs. Move deterministic scoring, paper-account capital handling, and trader watch-level normalization into Python modules; keep Codex prompts for reasoning-heavy DSA, technical, catalyst, and final narrative work.

**Tech Stack:** Python package under `src/trading_agent`, shell entrypoints under `src/scripts`, Codex prompt runners, JSON artifacts in `runtime/state/runs/<date>`, pytest.

---

## Priority Summary

| Priority | Optimization | Reason | Expected Impact |
| --- | --- | --- | --- |
| P0 | Add normalized `trader_watch_levels.json` | Trader needs direct price levels for intraday monitoring; current technical schema is usable but nested. | Immediate usability for intraday trader. |
| P0 | Separate paper buying power from Robinhood account snapshot | Current report shows Robinhood `$100` next to paper `$400000`; this can confuse sizing logic. | Prevents paper/live capital ambiguity. |
| P1 | Split `final_planner` into deterministic scoring, risk overlay, and narrative report | Final planner is slow and too broad; Python can handle scoring and caps more deterministically. | Faster final stage and more stable outputs. |
| P1 | Add `status` + `reason_code` data-status normalization | DSA `partial` due to closed market is not equivalent to provider failure. | Better fail-open/fail-closed decisions. |
| P2 | Add prompt progress logs | Long Codex stages currently look idle until completion. | Better observability during long real-data runs. |
| P2 | Reduce Codex calls for deterministic candidate steps | Quote/tradability/candidate merge can be mostly Python. | Lower runtime and less model variance. |

Out of scope: closed-market short-circuiting. The system should continue to support full research E2E even when the market is closed.

---

## File Structure

- Create `src/trading_agent/reporting/trader_watch_levels.py`
  - Builds a flat trader-facing watch-level artifact from `technical_signals.json`.
- Create `src/trading_agent/contracts/trader_watch_levels.py`
  - Validates required fields for trader-facing price levels.
- Modify `src/trading_agent/orchestration/premarket.py`
  - Writes `trader_watch_levels.json`; splits deterministic planner steps from final narrative.
- Modify `src/trading_agent/core/context.py`
  - Adds `trader_watch_levels_path` and paper-account output paths if missing.
- Modify `src/trading_agent/prompts/runtime_block.py`
  - Exposes `TRADER_WATCH_LEVELS_PATH`, `PAPER_ACCOUNT_PATH`, and paper capital semantics clearly.
- Create `src/trading_agent/planner/scoring.py`
  - Deterministic candidate scoring from DSA, Kronos, technical, quote, tradability, and catalyst inputs.
- Create `src/trading_agent/planner/risk_overlay.py`
  - Applies market calendar, risk tier, trading mode, paper buying power, and account conflict gates.
- Create `src/trading_agent/planner/data_status.py`
  - Normalizes `ok|partial|failed` plus `reason_code`.
- Modify `src/prompts/premarket/final_research.txt`
  - Turns final planner into report writing from precomputed scoring/risk artifacts.
- Modify `src/prompts/signals/dsa_scan.txt`, `src/prompts/technical/research.txt`, `src/prompts/premarket/catalyst_enrichment.txt`
  - Adds optional progress log writing.
- Test files:
  - `tests/reporting/test_trader_watch_levels.py`
  - `tests/planner/test_risk_overlay.py`
  - `tests/planner/test_scoring.py`
  - `tests/planner/test_data_status.py`
  - `tests/orchestration/test_premarket_outputs.py`

---

### Task 1: Add Normalized Trader Watch Levels

**Files:**
- Create: `src/trading_agent/reporting/trader_watch_levels.py`
- Create: `src/trading_agent/contracts/trader_watch_levels.py`
- Modify: `src/trading_agent/orchestration/premarket.py`
- Test: `tests/reporting/test_trader_watch_levels.py`

- [ ] **Step 1: Write failing tests for normalized price levels**

```python
from trading_agent.reporting.trader_watch_levels import build_trader_watch_levels


def test_build_trader_watch_levels_flattens_nested_technical_payload():
    payload = {
        "symbols": {
            "SMH": {
                "technical_action": "buy_bias",
                "confidence": 0.72,
                "key_levels": {
                    "reference_price": 619.96,
                    "supports": [527.87, 554.66, 590.82],
                    "resistances": [624.62, 642.77],
                    "range_low": 527.87,
                    "range_high": 642.77,
                },
                "long_setup": {
                    "trigger_above": 642.77,
                    "entry_zone": {"low": 590.82, "high": 619.96},
                    "invalidation_below": 590.82,
                    "target_1": 661.99,
                    "target_2": 681.20,
                    "do_not_chase_above": 674.80,
                    "status": "watch",
                },
                "short_setup": {
                    "trigger_below": 554.66,
                    "entry_zone": {"low": 541.85, "high": 554.66},
                    "invalidation_above": 624.62,
                    "target_1": 527.87,
                    "target_2": 378.00,
                    "status": "watch",
                    "notes": "Existing-long risk management only.",
                },
                "no_trade_zone": {"low": 590.82, "high": 642.77, "reason": "chop"},
            }
        }
    }

    result = build_trader_watch_levels(payload)

    assert result["schema_version"] == 1
    assert result["symbols"]["SMH"]["reference_price"] == 619.96
    assert result["symbols"]["SMH"]["buy_trigger_above"] == 642.77
    assert result["symbols"]["SMH"]["entry_low"] == 590.82
    assert result["symbols"]["SMH"]["entry_high"] == 619.96
    assert result["symbols"]["SMH"]["invalidation_below"] == 590.82
    assert result["symbols"]["SMH"]["target_1"] == 661.99
    assert result["symbols"]["SMH"]["target_2"] == 681.20
    assert result["symbols"]["SMH"]["no_trade_low"] == 590.82
    assert result["symbols"]["SMH"]["no_trade_high"] == 642.77
    assert result["symbols"]["SMH"]["risk_reduction_trigger_below"] == 554.66
    assert result["symbols"]["SMH"]["risk_reduction_only"] is True
```

- [ ] **Step 2: Run test and verify failure**

Run: `PYTHONPATH=src pytest tests/reporting/test_trader_watch_levels.py -v`

Expected: fails because `trading_agent.reporting.trader_watch_levels` does not exist.

- [ ] **Step 3: Implement flat watch-level builder**

Implement `build_trader_watch_levels(technical_payload)` to output:

```json
{
  "schema_version": 1,
  "symbols": {
    "SMH": {
      "reference_price": 619.96,
      "supports": [527.87, 554.66, 590.82],
      "resistances": [624.62, 642.77],
      "buy_trigger_above": 642.77,
      "entry_low": 590.82,
      "entry_high": 619.96,
      "invalidation_below": 590.82,
      "target_1": 661.99,
      "target_2": 681.2,
      "do_not_chase_above": 674.8,
      "no_trade_low": 590.82,
      "no_trade_high": 642.77,
      "risk_reduction_trigger_below": 554.66,
      "risk_reduction_only": true
    }
  }
}
```

- [ ] **Step 4: Wire artifact into premarket archive**

Write `runtime/state/runs/<date>/planner/trader_watch_levels.json` after technical completes and before final planner starts.

- [ ] **Step 5: Verify**

Run:

```bash
PYTHONPATH=src pytest tests/reporting/test_trader_watch_levels.py -v
env -u CODEX_EXEC_DRY_RUN ALLOW_WEEKEND_RUN=1 TRADING_MODE=paper ./src/scripts/entrypoints/run_premarket.sh
jq '.symbols | keys' runtime/state/runs/$(date +%F)/planner/trader_watch_levels.json
```

Expected: tests pass; real E2E writes `trader_watch_levels.json`.

---

### Task 2: Separate Paper Capital From Robinhood Account Snapshot

**Files:**
- Modify: `src/trading_agent/paper/broker.py`
- Modify: `src/trading_agent/planner/risk_overlay.py`
- Modify: `src/prompts/premarket/final_research.txt`
- Test: `tests/planner/test_risk_overlay.py`

- [ ] **Step 1: Write failing tests for paper buying power**

```python
from trading_agent.planner.risk_overlay import resolve_buying_power


def test_paper_mode_uses_paper_ledger_buying_power_not_robinhood_snapshot():
    result = resolve_buying_power(
        trading_mode="paper",
        paper_account={"cash": 400000.0, "equity": 400000.0},
        account_snapshot={"buying_power": 100.0},
    )

    assert result["buying_power"] == 400000.0
    assert result["source"] == "paper_account"
    assert result["real_account_buying_power"] == 100.0


def test_live_mode_uses_robinhood_snapshot():
    result = resolve_buying_power(
        trading_mode="live",
        paper_account={"cash": 400000.0},
        account_snapshot={"buying_power": 100.0},
    )

    assert result["buying_power"] == 100.0
    assert result["source"] == "robinhood_account_snapshot"
```

- [ ] **Step 2: Run test and verify failure**

Run: `PYTHONPATH=src pytest tests/planner/test_risk_overlay.py -v`

Expected: fails because `resolve_buying_power` is missing.

- [ ] **Step 3: Implement buying-power resolver**

Create `resolve_buying_power(...)` in `src/trading_agent/planner/risk_overlay.py`.

- [ ] **Step 4: Update final report prompt language**

Final report must display both:

```text
Paper buying power: <paper ledger cash>
Robinhood Agentic account buying power: <read-only real account snapshot>
```

In paper mode, position sizing must use paper buying power.

- [ ] **Step 5: Verify**

Run:

```bash
PYTHONPATH=src pytest tests/planner/test_risk_overlay.py -v
env -u CODEX_EXEC_DRY_RUN ALLOW_WEEKEND_RUN=1 TRADING_MODE=paper ./src/scripts/entrypoints/run_premarket.sh
rg "Paper buying power|Robinhood Agentic account buying power" runtime/state/runs/$(date +%F)/planner/daily_plan.md
```

Expected: report clearly separates paper and real account capital.

---

### Task 3: Split Final Planner Into Scoring, Risk Overlay, and Narrative

**Files:**
- Create: `src/trading_agent/planner/scoring.py`
- Create: `src/trading_agent/planner/risk_overlay.py`
- Modify: `src/trading_agent/orchestration/premarket.py`
- Modify: `src/prompts/premarket/final_research.txt`
- Test: `tests/planner/test_scoring.py`

- [ ] **Step 1: Write scoring tests**

```python
from trading_agent.planner.scoring import score_candidate


def test_score_candidate_combines_signal_layers_with_weights():
    score = score_candidate(
        symbol="SMH",
        dsa={"selected_candidates": [{"symbol": "SMH", "score": 86}]},
        kronos={"symbols": {"SMH": {"signal": "bearish", "confidence": 0.60}}},
        technical={"symbols": {"SMH": {"technical_action": "buy_bias", "priority_score": 82}}},
        quote={"symbols": {"SMH": {"last": 619.96, "change_pct": 2.0}}},
        catalyst={"symbols": {"SMH": {"catalyst_score": 55}}},
    )

    assert score["symbol"] == "SMH"
    assert score["score"] > 0
    assert score["components"]["dsa"] == 86
    assert score["components"]["technical"] == 82
```

- [ ] **Step 2: Implement deterministic scoring**

Use a simple transparent weighted model:

```text
DSA 35%
Technical 30%
Kronos 15%
Quote momentum/liquidity 10%
Catalyst 10%
```

Closed market and risk gates are not applied here; they belong in risk overlay.

- [ ] **Step 3: Implement risk overlay**

Risk overlay inputs:

```text
market_calendar
trading_mode
risk_tier
buying_power_resolution
account_snapshot
candidate_scores
```

Risk overlay outputs:

```text
allowed_actions
max_single_order_notional
max_daily_notional
today_allowlist
blocked_symbols
no_trade_reasons
```

- [ ] **Step 4: Reduce final prompt scope**

Update `final_research.txt` so Codex writes narrative from:

```text
candidate_scores.json
risk_overlay.json
trader_watch_levels.json
data_status_summary.json
```

It should not recompute scoring or risk caps.

- [ ] **Step 5: Verify runtime improvement**

Run:

```bash
env -u CODEX_EXEC_DRY_RUN ALLOW_WEEKEND_RUN=1 TRADING_MODE=paper ./src/scripts/entrypoints/run_premarket.sh
jq 'select(.stage=="final_planner")' runtime/logs/runs/$(date +%F)/pipeline.jsonl
```

Expected: final planner still generates report, but scoring/risk artifacts exist before it starts.

---

### Task 4: Normalize Data Status With Reason Codes

**Files:**
- Create: `src/trading_agent/planner/data_status.py`
- Modify: `src/trading_agent/orchestration/premarket.py`
- Modify: `src/prompts/signals/dsa_scan.txt`
- Test: `tests/planner/test_data_status.py`

- [ ] **Step 1: Write reason-code tests**

```python
from trading_agent.planner.data_status import normalize_layer_status


def test_market_closed_partial_is_not_provider_failure():
    result = normalize_layer_status(
        layer="dsa",
        raw_status={"quotes": "partial", "news": "ok", "historicals": "ok"},
        market_calendar={"trading_day": False, "session": "closed"},
    )

    assert result["status"] == "partial"
    assert result["reason_code"] == "market_closed"
    assert result["execution_blocking"] is True
    assert result["research_blocking"] is False
```

- [ ] **Step 2: Implement normalization**

Supported reason codes:

```text
market_closed
provider_partial
provider_failed
schema_invalid
mcp_unavailable
ok
```

- [ ] **Step 3: Write status summary artifact**

Write `runtime/state/runs/<date>/planner/data_status_summary.json`.

- [ ] **Step 4: Verify**

Run:

```bash
PYTHONPATH=src pytest tests/planner/test_data_status.py -v
env -u CODEX_EXEC_DRY_RUN ALLOW_WEEKEND_RUN=1 TRADING_MODE=paper ./src/scripts/entrypoints/run_premarket.sh
jq '.layers.dsa.reason_code' runtime/state/runs/$(date +%F)/planner/data_status_summary.json
```

Expected on closed-market test: `"market_closed"`.

---

### Task 5: Add Progress Logs For Long Prompt Stages

**Files:**
- Modify: `src/trading_agent/prompts/runtime_block.py`
- Modify: `src/prompts/signals/dsa_scan.txt`
- Modify: `src/prompts/technical/research.txt`
- Modify: `src/prompts/premarket/catalyst_enrichment.txt`
- Test: `tests/orchestration/test_premarket_outputs.py`

- [ ] **Step 1: Add runtime path**

Expose:

```text
PROGRESS_LOG_PATH=$RUN_LOGS_DIR/<run_kind>.progress.jsonl
```

to every Codex prompt.

- [ ] **Step 2: Update prompts**

Each long prompt must append JSONL entries shaped as:

```json
{"timestamp":"ISO-8601","run_kind":"technical_research","symbol":"SMH","status":"completed","message":"levels generated"}
```

- [ ] **Step 3: Verify progress logs exist**

Run:

```bash
env -u CODEX_EXEC_DRY_RUN ALLOW_WEEKEND_RUN=1 TRADING_MODE=paper ./src/scripts/entrypoints/run_premarket.sh
find runtime/logs/runs/$(date +%F) -name '*.progress.jsonl' -maxdepth 1 -type f -print
```

Expected: progress logs exist for DSA, technical, and catalyst stages.

---

### Task 6: Convert Deterministic Candidate Steps Away From Codex

**Files:**
- Create: `src/trading_agent/planner/quote_snapshot.py`
- Create: `src/trading_agent/planner/tradability.py`
- Modify: `src/trading_agent/orchestration/premarket.py`
- Test: `tests/planner/test_quote_snapshot.py`, `tests/planner/test_tradability.py`

- [ ] **Step 1: Identify deterministic fields**

Keep these in Python:

```text
last price
previous close
change percent
average volume
tradability flags
blocked-by-account flags
candidate universe merge
```

- [ ] **Step 2: Add tests for quote snapshot from market-feed artifacts**

Use small fixture market-feed JSON to verify deterministic extraction.

- [ ] **Step 3: Add tests for tradability rules**

Verify symbols are blocked when:

```text
already traded today
account snapshot missing required data
symbol not in universe
price/liquidity missing
```

- [ ] **Step 4: Replace Codex prompt calls for deterministic candidate steps**

Remove Codex calls for quote/tradability where the Python version produces equivalent schema.

- [ ] **Step 5: Verify runtime**

Run:

```bash
env -u CODEX_EXEC_DRY_RUN ALLOW_WEEKEND_RUN=1 TRADING_MODE=paper ./src/scripts/entrypoints/run_premarket.sh
jq '[.stage,.status,.elapsed_seconds]' runtime/logs/runs/$(date +%F)/pipeline.jsonl
```

Expected: fewer Codex child processes; same final artifacts.

---

## Recommended Execution Order

1. Task 1 and Task 2 in parallel.
2. Task 4 after Task 2, because risk/report status should use normalized reason codes.
3. Task 3 after Task 1, Task 2, and Task 4, because final planner consumes their artifacts.
4. Task 5 after Task 3, because progress log paths should reflect the new stage split.
5. Task 6 last, because it changes pipeline behavior most and should be benchmarked against the stabilized outputs.

## Verification Contract

Every task must pass:

```bash
PYTHONPATH=src pytest tests -q
env -u CODEX_EXEC_DRY_RUN ALLOW_WEEKEND_RUN=1 TRADING_MODE=paper ./src/scripts/entrypoints/run_premarket.sh
```

The E2E run must produce:

```text
runtime/state/runs/<date>/planner/daily_plan.json
runtime/state/runs/<date>/planner/daily_plan.md
runtime/state/runs/<date>/planner/dynamic_allowlist.json
runtime/state/runs/<date>/planner/today_allowlist.txt
runtime/state/runs/<date>/planner/trader_watch_levels.json
runtime/state/runs/<date>/archive/premarket_report.json
runtime/logs/runs/<date>/pipeline.jsonl
```

`runtime/logs/runs/<date>/errors.log` must be empty unless the test intentionally exercises a fail-closed path.

## Commit Strategy

Commit after each task:

```bash
git add <changed files>
git commit -m "feat: add trader watch levels"
git commit -m "fix: separate paper and account buying power"
git commit -m "feat: split premarket planner scoring and risk"
git commit -m "feat: normalize premarket data status"
git commit -m "feat: add premarket progress logs"
git commit -m "refactor: move deterministic candidate steps to python"
```

Push after each successful E2E, or at minimum after Task 3 and Task 6.

