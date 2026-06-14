# Trading Agent Package Rearchitecture Design

Date: 2026-06-14
Repo: `/Users/puyihao/Documents/trading`
Status: Approved direction, pending implementation plan

## Goal

Reorganize the current Robinhood Codex trading automation into a real Python package with clear data, signal, orchestration, safety, and reporting boundaries.

The redesigned system should keep the current safety behavior intact while making premarket analysis faster, easier to extend, and easier to audit. Shell scripts will remain as compatibility launchers, but Python will own the runtime orchestration.

## Current State

The repository already has a sensible workflow:

```text
DSA signal scan
  -> Kronos signal scan
  -> market feed collection
  -> technical research
  -> main premarket planner
  -> intraday trader
  -> postmarket review
```

The problem is that responsibilities are spread across `src/scripts/`, `src/prompts/`, `src/config/`, and JSON files under `runtime/state/`. Schemas are mostly embedded in prompt text, path/runtime logic lives in shell, and each layer owns parts of data access or output contracts independently.

The current tests and safety checks pass, so this is a structural rearchitecture rather than a bug fix.

## Primary Requirements

1. Convert the project into a package-oriented architecture under `trading_agent/`.
2. Keep existing shell entrypoints working for cron and launchd.
3. Extract data collection into one reusable market context layer.
4. Let DSA, Kronos, and technical analysis consume the shared collected data instead of each owning separate data collection paths.
5. Run independent premarket layers in parallel where safe.
6. Preserve technical price levels in final outputs for intraday trader use.
7. Centralize scoring and final decision weights in the premarket planner.
8. Keep all analyzer outputs advisory only; no analyzer can authorize a trade by itself.
9. Archive each premarket report in both human-readable and machine-readable form.
10. Preserve current safety defaults: paper mode, risk tier caps, kill switch, long-only execution, limit orders, and prompt-gated live order placement.

## Non-Goals

- No live-trading behavior change in the first package migration.
- No removal of existing shell commands used by cron or launchd.
- No automatic `RISK_TIER` increase.
- No direct trade execution from DSA, Kronos, market feed, or technical research.
- No short selling. Technical short-side fields remain risk-reduction guidance for existing long positions only.
- No large provider expansion in the first pass. Provider interfaces should be ready for new sources, but initial behavior can keep the current yfinance and Codex/MCP usage.

## Recommended Architecture

Create this package layout:

```text
trading_agent/
  __init__.py
  cli.py
  core/
    config.py
    context.py
    io.py
    locks.py
    logging.py
    time.py
  contracts/
    market_feed.py
    dsa.py
    kronos.py
    technical.py
    daily_plan.py
    reports.py
  data/
    universe.py
    providers/
      base.py
      yfinance_provider.py
    market_context.py
    charts.py
  signals/
    dsa.py
    kronos.py
    technical.py
  src/prompts/
    codex.py
    runtime_block.py
  orchestration/
    premarket.py
    intraday.py
    postmarket.py
    tasks.py
  reporting/
    premarket.py
    postmarket.py
    archive.py
  safety/
    gates.py
    risk.py
    allowlist.py

src/scripts/
  run_premarket.sh
  run_intraday.sh
  run_postmarket.sh
  run_market_feed_collection.sh
  run_kronos_premarket_scan.sh
  run_technical_research.sh
```

Shell scripts become thin wrappers around `python -m trading_agent ...`. Existing standalone scripts can remain during migration, but long-term logic should move into package modules.

## Data Collection Boundary

The current layers should be separated into collection versus analysis:

```text
Unified Market Context
  -> quotes
  -> multi-timeframe OHLCV
  -> charts
  -> news and catalysts
  -> earnings calendar
  -> filings
  -> market regime proxies
  -> tradability/account snapshots when the run is allowed to use broker read tools

DSA Analyzer        consumes theme, catalyst, quote, news, and historical context
Kronos Analyzer     consumes normalized OHLCV
Technical Analyzer  consumes OHLCV, charts, news, and selected context
Premarket Planner   consumes all analyzer outputs and applies gates, weights, and final ranking
```

`Market Feed` is not a strategy layer. It is the raw and normalized data collection layer. DSA, Kronos, and technical research should not each reinvent symbol parsing, date handling, artifact paths, or raw market-data fetching.

The first implementation can still call Codex for DSA and technical analysis, but their prompts should receive paths to a shared `MarketContext` bundle instead of being responsible for discovering all data independently.

## Premarket Dependency Graph

The package-owned premarket orchestration should use a dependency graph:

```text
Market Context Collection
        |
        v
DSA signal scan       Kronos scan
        \              /
         \            /
          v          v
      Technical research
              |
              v
       Premarket planner
              |
              v
       Report archive
```

If DSA can safely use only public web/search or broker read tools independent of collected artifacts, DSA may run concurrently with market context collection. Kronos should prefer the shared OHLCV bundle when present; until then it can run from its current yfinance path. The implementation plan should make this transition explicit:

1. preserve current behavior first
2. introduce shared market context
3. migrate Kronos to read shared OHLCV
4. migrate DSA and technical prompts to reference shared context

Target steady-state graph:

```text
Market Context Collection
        |
        +--> DSA Analyzer
        +--> Kronos Analyzer
        +--> Technical Analyzer
                 |
                 v
          Premarket Planner
                 |
                 v
          Report Archive
```

In this steady state, DSA, Kronos, and technical can run in parallel after shared data collection finishes. If a future DSA implementation has independent data sources, it can be marked as a parallel root task.

## Analyzer Responsibilities

### DSA Signal Analyzer

Purpose:

- identify hot themes
- evaluate event-driven catalysts
- score trend, pullback, breakout, quality, and leader behavior
- block hype-only, stale, risky, or low-quality candidates

Input:

- universe
- market context quotes and prior close
- news and catalyst summaries
- available historical context
- optional wash-sale blocks
- DSA strategy weights

Output:

- `runtime/state/runs/<date>/signals/dsa_signals.json`
- advisory `promote`, `neutral`, `demote`, or `block` guidance
- no account-state changes and no trade authorization

### Kronos Analyzer

Purpose:

- produce directional and volatility forecasts from time-series data
- help classify setup bias as breakout, pullback, chop, or avoid
- provide confidence and forecast risk flags

Input:

- normalized OHLCV from shared market context
- Kronos runtime config
- fixed local Kronos environment

Output:

- `runtime/state/runs/<date>/signals/kronos_signals.json`
- advisory forecast context only
- no trade authorization

### Technical Analyzer

Purpose:

- interpret multi-timeframe structure
- identify actionable long setup levels
- identify no-trade zones
- identify risk-reduction levels for existing long positions
- produce execution-aware levels for the intraday trader

Input:

- OHLCV
- charts
- news/catalyst context
- repo-owned trading skills
- DSA/Kronos context when useful

Output:

- `runtime/state/runs/<date>/signals/technical_signals.json`
- `trader_watch_levels` extracted into final daily plan and reports
- no direct trade authorization

### Premarket Planner

Purpose:

- apply hard gates
- score candidates
- combine DSA, Kronos, technical, market regime, quality, and risk fit
- write official daily plan and dynamic allowlist
- archive the report

Input:

- all analyzer outputs
- account and broker read data when available
- risk rules
- runtime mode
- universe

Output:

- `runtime/state/today_allowlist.txt`
- `runtime/state/dynamic_allowlist.json`
- `runtime/state/daily_plan.json`
- `runtime/state/daily_plan.md`
- `runtime/reports/premarket/YYYY-MM-DD.json`
- `runtime/reports/premarket/YYYY-MM-DD.md`
- one decision record in `runtime/logs/decisions.jsonl`

## Scoring and Weights

Final scoring belongs to the premarket planner, not to individual analyzers.

Hard gates run before scoring:

- symbol outside `src/config/universe.txt`
- missing or stale required data
- Robinhood tradability failure when checked
- account ambiguity
- risk tier cap violation
- no-trade market regime
- earnings/gap/liquidity/major negative-news block
- DSA hard block that is not explicitly invalidated by fresher verified evidence
- price inside technical no-trade zone for executable candidates

Initial weighted scoring:

```text
Market regime and liquidity:        15%
DSA theme and catalyst quality:     25%
Technical setup and price levels:   25%
Kronos forecast context:            15%
Fundamental and trap screen:        10%
Portfolio, account, and risk fit:   10%
```

The planner should emit component scores:

```json
{
  "symbol": "NVDA",
  "final_score": 86,
  "components": {
    "market_regime": 12,
    "dsa": 22,
    "technical": 24,
    "kronos": 11,
    "fundamental_quality": 8,
    "risk_fit": 9
  },
  "hard_blocks": [],
  "decision": "tradable_candidate"
}
```

Kronos should influence ranking and risk context but should not dominate execution. Technical and DSA receive higher weights because they answer the two most important premarket questions: why this symbol today, and where can it be acted on safely.

## Technical Price Levels in Final Outputs

Technical price levels must be carried into final outputs for the intraday trader. They must not remain only inside `runtime/state/runs/<date>/signals/technical_signals.json`.

`runtime/state/daily_plan.json`, `runtime/reports/premarket/YYYY-MM-DD.json`, and the human-readable premarket report should include:

```json
{
  "trader_watch_levels": {
    "NVDA": {
      "current_context": "breakout_pullback_watch",
      "data_status": "ok",
      "confidence": "medium",
      "key_levels": {
        "premarket_high": 0,
        "prior_close": 0,
        "support": [0, 0],
        "resistance": [0, 0],
        "vwap_reference": 0
      },
      "long_setup": {
        "entry_zone": {"low": 0, "high": 0},
        "trigger_above": 0,
        "do_not_chase_above": 0,
        "invalidation_below": 0,
        "first_target": 0,
        "second_target": 0
      },
      "risk_reduction_setup": {
        "trim_trigger_below": 0,
        "hard_warning_below": 0,
        "reason": "breakout failure or range rejection"
      },
      "no_trade_zone": {
        "low": 0,
        "high": 0,
        "reason": "middle of noisy range"
      },
      "execution_notes": [
        "Only consider long if price holds above trigger with fresh quote confirmation.",
        "Do not chase above do_not_chase_above."
      ]
    }
  }
}
```

Rules:

- `long_setup` may support buy evaluation only when all hard gates pass.
- `risk_reduction_setup` applies only to existing long positions. It never authorizes opening shorts.
- `no_trade_zone` must suppress executable candidate selection unless the planner explicitly records why it is obsolete.
- `do_not_chase_above` must be preserved for intraday checks.
- Every level set must include data status and confidence.
- If levels are stale, missing, or low confidence, intraday should treat the symbol as watch-only or no-action.

The markdown report should include a trader-readable section:

```text
NVDA
- Bias: watch for pullback long
- Entry zone: 124.20-125.10
- Trigger above: 126.30
- Do not chase above: 128.00
- Invalidation: below 122.80
- No-trade zone: 125.20-126.20
- First target: 129.50
```

## Reporting and Archive

Each premarket run should archive what was known and decided:

```text
runtime/reports/
  premarket/
    YYYY-MM-DD.md
    YYYY-MM-DD.json
  postmarket/
    YYYY-MM-DD.md
```

The archive should include:

- runtime snapshot
- data source status
- market regime
- selected symbols
- blocked symbols
- weighted scores
- analyzer summaries
- technical price levels
- no-trade reasons
- risk tier and notional caps
- final daily plan summary

Generated reports may contain operational details and should remain ignored unless the user explicitly wants selected archives committed.

## Migration Plan Outline

Detailed implementation should be handled in a separate implementation plan, but the work should be sequenced this way:

1. Create package skeleton and CLI while keeping shell entrypoints compatible.
2. Move runtime context, paths, PT date/time, env loading, locks, and JSON helpers into `trading_agent.core`.
3. Add contract validators for market feed, DSA, Kronos, technical signals, daily plan, and reports.
4. Move market-feed collection code into `trading_agent.data` and keep `src/scripts/data/collect_market_feed.py` as a wrapper.
5. Move Kronos generation code into `trading_agent.signals.kronos` and keep the existing runner compatible.
6. Add `trading_agent.orchestration.premarket` with task dependency handling and safe failure degradation.
7. Add report archiving and wire technical price levels into daily plan and premarket reports.
8. Update tests from script-only checks to package API tests plus wrapper compatibility tests.
9. Update README and setup docs to describe package architecture and extension points.

## Testing Strategy

Keep current tests passing throughout migration. Add focused tests for:

- env layering and runtime context
- path resolution and report archive paths
- universe parsing
- market context manifest schema
- DSA, Kronos, and technical contract validation
- planner score calculation
- technical price level extraction into `daily_plan.json`
- premarket task ordering and parallel execution
- failure degradation when one advisory analyzer fails
- shell wrapper compatibility

Dry-run validation should include:

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
./src/scripts/safety/check_safety.sh
ALLOW_WEEKEND_RUN=1 KRONOS_USE_MOCK=1 CODEX_EXEC_DRY_RUN=1 ./src/scripts/entrypoints/run_premarket.sh
```

## Open Implementation Decisions

1. Whether to introduce a packaging file such as `pyproject.toml` immediately or keep imports repo-local in the first task.
2. Whether generated report archives should stay ignored by default or support an explicit command to commit selected reports.
3. Whether DSA remains Codex-prompt-based in phase one or receives a deterministic Python scoring adapter first.
4. Whether technical analysis stays prompt-based with schema validation or moves toward deterministic extraction from OHLCV over time.

Recommended defaults:

- add `pyproject.toml` early so package imports and tests are stable
- keep reports ignored by default
- keep DSA and technical prompt-based initially
- centralize schemas and score calculation before replacing model-driven analysis
