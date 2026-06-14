# Premarket Workflow Setup

## Current Flow

```text
account_snapshot
  -> market_context
  -> parallel: DSA / Kronos / technical / market_calendar / core_quotes
  -> candidate_snapshot
  -> parallel: candidate_quotes / tradability / catalyst_enrichment
  -> final_premarket
  -> archive
```

`account_snapshot` runs first because current positions and open orders are needed by later quote and candidate stages.

## Main Command

```bash
ALLOW_WEEKEND_RUN=1 CODEX_EXEC_DRY_RUN=1 ./scripts/entrypoints/run_premarket.sh
```

Use `ALLOW_WEEKEND_RUN=1` only for testing outside market weekdays.

## Prompt Layout

```text
prompts/
  premarket/
    account_snapshot.txt
    market_calendar.txt
    quote_snapshot_core.txt
    quote_snapshot_candidates.txt
    tradability_candidates.txt
    catalyst_enrichment.txt
    final_research.txt
  signals/
    dsa_scan.txt
  technical/
    research.txt
  intraday/
    check.txt
  postmarket/
    summary.txt
```

## Script Layout

```text
scripts/
  entrypoints/
  data/
  kronos/
  skills/
  safety/
  lib/
```

There are no top-level script wrappers. Use the subdirectory paths directly.

## Daily Output Layout

```text
state/runs/<date>/
  market_feed/
  signals/
    dsa_signals.json
    kronos_signals.json
    technical_signals.json
  planner/
    account_snapshot.json
    market_calendar.json
    quote_snapshot_core.json
    candidate_snapshot.json
    quote_snapshot_candidates.json
    tradability_snapshot.json
    catalyst_snapshot.json
    daily_plan.json
    daily_plan.md
  archive/

logs/runs/<date>/
  pipeline.jsonl
  codex_runs.log
  errors.log
  decisions.jsonl
```

## Verification

```bash
python3 -m unittest tests.test_premarket_orchestration -v
python3 -m unittest tests.test_collect_market_feed tests.test_kronos_generate_signals tests.test_technical_signal_schema -v
./scripts/safety/check_safety.sh
```
