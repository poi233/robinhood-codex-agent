# Premarket Skill Feed Integration Design

Date: 2026-06-13
Repo: `/Users/puyihao/Documents/trading`
Status: Draft for user review

## Goal

Add a portable, repo-owned market-data and research pipeline that feeds local trading skills into the existing premarket workflow.

The system must:

1. keep the skill source of truth inside this repository
2. install real copied versions of the skills into both `$HOME/.agents/skills` and `~/.codex/skills`
3. collect both chart images and structured market/news data
4. run a dedicated technical-analysis step that explicitly uses the repo-owned skills
5. emit structured price levels that the intraday checker can use for actionable buy, hold, trim, or avoid decisions
6. remain long-only in execution, with short logic used only for managing existing long positions

## Primary Requirements

1. The repository owns the canonical skill definitions.
2. The repository must remain portable to a new machine.
3. Skills must be copied, not symlinked, into user-level skill directories.
4. The new data feed must support both scheduled premarket runs and ad hoc single-symbol research.
5. The first implementation must produce both rendered chart images and structured OHLCV/news artifacts.
6. The first implementation must use public data sources by default, while allowing manual visual supplementation later.
7. News scope for phase 1 is limited to:
   - news
   - earnings calendar items
   - company filings / SEC items
8. Kronos is out of scope for phase 1.
9. Social sentiment is out of scope for phase 1.
10. The critical trading path must not depend on casebook writing.

## Non-Goals

- No Kronos integration in this phase
- No multi-service or daemon architecture
- No social media sentiment ingestion
- No broker-native screenshot acquisition as the default source
- No short selling, inverse execution, or new short entries
- No automatic casebook updates that can block `daily_plan.json`
- No direct order placement from the technical-analysis step

## Recommended Approach

Three implementation shapes were considered:

1. Prompt-centric direct feed:
   - collector outputs raw artifacts
   - main premarket prompt interprets everything directly
2. Layered artifact plus skill pipeline:
   - collector outputs normalized artifacts
   - dedicated technical-analysis step explicitly uses repo skills
   - main premarket planner consumes normalized technical output
3. Multi-service pipeline:
   - collector, analysis, and planner split into multiple standalone services

Recommended: option 2.

Why:

- keeps the repository portable
- gives the skills a stable explicit invocation path
- prevents `premarket_research.txt` from absorbing all raw interpretation logic
- creates a clean contract between deterministic data collection and model-driven analysis
- leaves a future insertion point for Kronos without redesigning the pipeline

## Skill Scope

The repository-owned skill pack for phase 1 includes:

1. `chan-structure-trading`
2. `brooks-trading-range-price-action`
3. `equity-fundamentals-analysis`
4. `trading-research-casebook-maintenance`

Each skill must be copied into the repository with its full support files, not only `SKILL.md`.

Expected contents per skill:

- `SKILL.md`
- `references/` when present
- `casebook/` when present
- `templates/` when present

Behavioral role in the trading chain:

- `chan-structure-trading`: multi-timeframe structure, centers, type 1/2/3 signals
- `brooks-trading-range-price-action`: breakout quality, range/trend logic, pullback and failure setups
- `equity-fundamentals-analysis`: catalyst quality and obvious company-quality red flags
- `trading-research-casebook-maintenance`: reusable pattern capture only, outside the critical trading path

## Repository Layout

Recommended new layout:

```text
.agents/
  skills/
    chan-structure-trading/
    brooks-trading-range-price-action/
    equity-fundamentals-analysis/
    trading-research-casebook-maintenance/

src/scripts/
  install_repo_skills.sh
  verify_repo_skills.sh
  collect_market_feed.py
  run_market_feed_collection.sh
  run_technical_research.sh
  run_symbol_research.sh

src/prompts/
  technical_research.txt

runtime/state/
  market_feed/
    YYYY-MM-DD/
      charts/
      ohlcv/
      news/
      manifest.json
  technical_signals.json

docs/setup/
  repo-skills.md
  market-feed.md

tests/
  test_install_repo_skills.py
  test_collect_market_feed.py
  test_technical_signal_schema.py
```

## Skill Packaging and Installation

`.agents/skills/` is the single source of truth.

The installer must copy from the repository source into both destinations:

- `$HOME/.agents/skills`
- `~/.codex/skills`

Installation rules:

1. copy real files, not symlinks
2. replace existing same-name skill directories
3. preserve directory contents including references, casebook, and templates
4. fail clearly if a source skill directory is incomplete
5. provide a verification step after installation

Verification rules:

1. each expected installed skill exists in both destinations
2. each installed skill contains `SKILL.md`
3. required subdirectories present in the source are also present in the installed copies
4. verification returns a clear pass/fail summary

The installed copies are for portability and convenience across threads or repos. The pipeline logic in this repository should still explicitly reference the repo-owned skill pack as the authoritative source.

## Premarket Data Flow

The scheduled premarket flow becomes:

```text
src/config/universe.txt
  -> DSA signal scan
  -> market-feed collection
  -> technical research using repo skills
  -> main premarket planner
  -> daily plan and dynamic allowlist
```

There are four stages:

1. Collector
2. Technical Analysis Step
3. Main Premarket Planner
4. Research Memory

### Stage 1: Collector

Responsibilities:

- read the requested symbol set
- fetch OHLCV data for multiple timeframes
- render multi-timeframe chart images
- gather news, earnings, and filing summaries
- write a normalized artifact bundle under `runtime/state/runs/<date>/market_feed/`

Inputs:

- `src/config/universe.txt`
- run date
- optional manual symbol override
- optional timeframe override

Default timeframes:

- `1w`
- `1d`
- `1h`
- `15m`

Default artifact layout:

```text
runtime/state/market_feed/<YYYY-MM-DD>/
  charts/
    NVDA/
      weekly.png
      daily.png
      hourly.png
      intraday_15m.png
  ohlcv/
    NVDA/
      weekly.json
      daily.json
      hourly.json
      intraday_15m.json
  news/
    NVDA.json
    market_summary.json
  manifest.json
```

Artifact purpose:

- `charts/`: visual structure review for Chan and Brooks
- `ohlcv/`: machine-stable input for automation and tests
- `news/`: catalyst and context layer for fundamentals and event interpretation
- `manifest.json`: collection completeness and status boundary

Collector behavior rules:

1. partial symbol failures are allowed
2. one symbol failure must not abort the full premarket run
3. collector status must be explicit and machine-readable
4. the collector does not make trade recommendations

### Stage 2: Technical Analysis Step

This is a dedicated, separate step. It must not be folded back into `src/prompts/premarket/final_research.txt`.

Responsibilities:

- read collected charts, OHLCV, and news artifacts
- explicitly use the repo-owned skills
- classify the technical state of each symbol
- generate execution-aware levels for intraday use
- write `runtime/state/runs/<date>/signals/technical_signals.json`

Inputs:

- `runtime/state/runs/<date>/market_feed/charts/...`
- `runtime/state/runs/<date>/market_feed/ohlcv/...`
- `runtime/state/runs/<date>/market_feed/news/...`
- `.agents/skills/...`
- optional `runtime/state/runs/<date>/signals/dsa_signals.json`

Skill usage split:

- `chan`: centers, trends, type 1/2/3 buy-sell logic
- `brooks`: breakout quality, pullback logic, failure logic, range/trend judgment
- `fundamentals`: whether the news flow is supportive, neutral, cautionary, or negative
- `casebook-maintenance`: deferred to post-analysis memory capture only

### Stage 3: Main Premarket Planner

The main premarket planner remains the final arbitration layer.

It continues to own:

- market regime judgment
- sector judgment
- DSA blending
- Robinhood account and buying-power checks
- open-order and position checks
- tradability and quote checks
- risk-tier enforcement
- final allowlist and daily plan generation

New input:

- `runtime/state/runs/<date>/signals/technical_signals.json`

Consumption rules:

1. `buy_bias` may increase priority but cannot bypass risk or account gates
2. `sell_bias` may bias toward trim, no-add, caution, or block behavior for an existing holding
3. `hold`, `observe`, or `avoid` should keep a symbol out of executable candidates unless stronger current evidence appears
4. if the technical analysis is partial, failed, or unclear, the planner must downgrade confidence rather than assume clarity

### Stage 4: Research Memory

Casebook capture is not part of the critical trading path.

Responsibilities:

- preserve reusable patterns
- preserve recurring failure modes
- preserve multi-timeframe edge cases

Rules:

1. casebook updates may run after the critical trade outputs are already written
2. casebook failures must not block `daily_plan.json`
3. the trading path must remain complete without a casebook update

## Manual Research Entry Point

The system must also support manual single-symbol use.

Recommended behavior:

- operator runs `src/scripts/data/run_symbol_research.sh SYMBOL`
- collector builds a feed bundle for that symbol
- technical research runs on that symbol
- outputs are reviewable without a full scheduled premarket run

This path is for discretionary research and debugging. It should share the same collector and technical-analysis codepaths as the scheduled flow.

## Data Contracts

Two files define the key boundary between collection, analysis, and planning:

1. `runtime/state/runs/<date>/market_feed/manifest.json`
2. `runtime/state/runs/<date>/signals/technical_signals.json`

### `runtime/state/runs/<date>/market_feed/manifest.json`

Suggested schema:

```json
{
  "date": "YYYY-MM-DD",
  "generated_at": "ISO-8601",
  "run_mode": "scheduled|manual",
  "source_universe": "src/config/universe.txt",
  "requested_symbols": ["NVDA", "SPY"],
  "completed_symbols": ["NVDA"],
  "failed_symbols": ["SPY"],
  "timeframes": ["1w", "1d", "1h", "15m"],
  "sources": {
    "ohlcv": "yfinance",
    "news": "public_news",
    "earnings": "public_calendar",
    "filings": "sec"
  },
  "data_status": "ok|partial|failed",
  "artifacts": {
    "charts_root": "runtime/state/market_feed/YYYY-MM-DD/charts",
    "ohlcv_root": "runtime/state/market_feed/YYYY-MM-DD/ohlcv",
    "news_root": "runtime/state/market_feed/YYYY-MM-DD/news"
  },
  "symbol_status": {
    "NVDA": {
      "ohlcv": "ok",
      "charts": "ok",
      "news": "ok",
      "earnings": "ok",
      "filings": "ok",
      "notes": ""
    }
  },
  "notes": "short text"
}
```

Purpose:

- state whether collected artifacts are complete enough to analyze
- define status per symbol and per artifact class
- allow downstream steps to degrade safely

### `runtime/state/runs/<date>/signals/technical_signals.json`

This file must include both directional judgment and execution-aware price levels.

`short_setup` in phase 1 is not for opening short positions. It is only for managing existing long positions:

- trim bias
- sell bias
- no-add condition
- caution or block behavior

Suggested schema:

```json
{
  "date": "YYYY-MM-DD",
  "generated_at": "ISO-8601",
  "source_feed_manifest": "runtime/state/market_feed/YYYY-MM-DD/manifest.json",
  "analysis_status": "ok|partial|failed",
  "symbols": {
    "NVDA": {
      "technical_phase": "range|up_transition|up_trend|down_transition|down_trend|unclear",
      "technical_action": "hold|buy_bias|sell_bias|avoid|observe",
      "priority_score": 0,
      "timeframe_stack": {
        "higher": "1w",
        "execution": "1d",
        "lower": "1h"
      },
      "timeframe_alignment": "aligned|mixed|conflicted",
      "key_levels": {
        "reference_price": 0.0,
        "supports": [0.0],
        "resistances": [0.0],
        "range_low": 0.0,
        "range_high": 0.0
      },
      "long_setup": {
        "status": "active|watch|invalid",
        "setup_type": "breakout|pullback|retest|none",
        "trigger_above": 0.0,
        "entry_zone": {
          "low": 0.0,
          "high": 0.0
        },
        "invalidation_below": 0.0,
        "target_1": 0.0,
        "target_2": 0.0,
        "do_not_chase_above": 0.0,
        "notes": "short text"
      },
      "short_setup": {
        "status": "active|watch|invalid",
        "setup_type": "breakdown|failed_breakout|fade|none",
        "trigger_below": 0.0,
        "entry_zone": {
          "low": 0.0,
          "high": 0.0
        },
        "invalidation_above": 0.0,
        "target_1": 0.0,
        "target_2": 0.0,
        "do_not_chase_below": 0.0,
        "notes": "short text"
      },
      "no_trade_zone": {
        "low": 0.0,
        "high": 0.0,
        "reason": "short text"
      },
      "chan": {
        "signal": "none|type1|type2|type3",
        "state": "trend_continuation|center_extension|reversal_attempt",
        "invalidation": "short text",
        "next_confirmation": "short text"
      },
      "brooks": {
        "setup": "none|breakout_continuation|breakout_pullback|failed_breakout_fade|h1|h2|l1|l2|range",
        "entry_style": "breakout|pullback|retest|fade|none",
        "target_logic": "nearest_magnet|measured_move|range_opposite_side|none",
        "downgrade_condition": "short text"
      },
      "fundamentals": {
        "event_bias": "supportive|neutral|caution|negative",
        "event_type": "earnings|filing|news|none",
        "quality_flag": "clear|watch|red_flag"
      },
      "decision_rationale": "short text",
      "confidence": 0.0
    }
  },
  "notes": "short text"
}
```

Semantic mapping:

- `振荡期不动`:
  - `technical_phase=range`
  - `technical_action=hold|observe`
  - `no_trade_zone` must be populated
- `将进入上升阶段了买入`:
  - `technical_phase=up_transition`
  - `technical_action=buy_bias`
  - `long_setup` must contain `trigger_above` or a valid pullback entry zone
- `将进入下降阶段了卖出`:
  - `technical_phase=down_transition`
  - `technical_action=sell_bias`
  - `short_setup` must contain the key exit-risk levels for an existing long

## Failure Handling

Collector failures:

- if one symbol fails, mark that symbol partial or failed and continue
- if the whole collector fails, mark `data_status=failed`

Technical-analysis failures:

- if one symbol lacks sufficient material, output:
  - `technical_phase=unclear`
  - `technical_action=observe|avoid`
- if the whole technical step fails, the main planner must degrade to existing DSA plus current planner behavior

Execution-level failures:

- if a symbol lacks critical long-entry levels, no long setup may be considered active
- if a symbol lacks critical short-risk levels, no trim or sell bias may be triggered from the technical layer

Casebook failures:

- log and continue
- never block daily-plan outputs

## Testing Strategy

Phase 1 must include tests for:

1. skill installation
   - repository skills copy correctly into both user destinations
   - copied directories contain `SKILL.md` and required subdirectories
2. collector contract
   - expected artifact directories are created
   - manifest schema is correct
   - partial failures are encoded safely
3. technical signal contract
   - `technical_signals.json` schema includes:
     - `long_setup`
     - `short_setup`
     - `no_trade_zone`
     - critical key-level fields
4. planner integration
   - planner reads `technical_signals.json`
   - planner degrades safely on partial or failed analysis
5. manual research entrypoint
   - single-symbol research path builds the same contract outputs
6. dry-run smoke path
   - `run_premarket.sh` completes the new chain without real trading actions

## Rollout Order

Implementation should proceed in this order:

1. add repo-owned skills
2. add installer and verifier
3. add collector layer
4. add technical-analysis step
5. integrate technical outputs into main premarket planning
6. add manual single-symbol research entrypoint
7. add tests and docs

This order preserves a working, testable system after each stage.

## Out-of-Scope Extensions Reserved For Later

- Kronos insertion after the collector or alongside technical research
- social sentiment sources
- broker-native screenshots as a primary source
- fully automated casebook writing
- advanced probability distributions or portfolio sizing in `technical_signals.json`
- direct execution logic from the technical-analysis step

## Approval Gate

This design is ready for implementation planning once the user confirms:

1. the four-stage premarket flow
2. the repository skill-pack strategy
3. the collector artifact layout
4. the `technical_signals.json` contract with dual long/short scenarios
5. the rule that `short_setup` is only for managing existing long positions in phase 1
