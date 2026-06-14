# Market Feed And Technical Research

The market feed layer is deterministic local data collection. It writes market context used by the
technical research prompt and the final premarket planner.

## Runtime Role

Premarket calls market context before advisory prompts:

```text
premarket
  -> account_snapshot
  -> market_context
  -> parallel: DSA / Kronos / technical / market calendar / core quotes
  -> candidate_merge
  -> parallel: candidate quotes / tradability / catalysts
  -> final planner
```

The technical layer depends on `state/runs/<date>/market_feed/manifest.json`. If market feed data is
missing or incomplete, technical research fails closed and writes a conservative failed payload when
possible.

## Key Outputs

```text
state/runs/<date>/market_feed/
  manifest.json
  charts/
  ohlcv/
  news/

state/runs/<date>/signals/technical_signals.json
```

## Scheduled Flow

The full premarket pipeline runs market feed and technical research automatically:

```bash
./scripts/entrypoints/run_premarket.sh
```

Layer flags:

```bash
ENABLE_MARKET_FEED_LAYER=0 ./scripts/entrypoints/run_premarket.sh
ENABLE_TECHNICAL_SIGNAL_LAYER=0 ./scripts/entrypoints/run_premarket.sh
```

## Manual Flow

Collect market feed for the configured universe:

```bash
./scripts/data/run_market_feed_collection.sh
```

Run technical research against the current market feed:

```bash
./scripts/data/run_technical_research.sh
```

Collect and analyze one symbol:

```bash
./scripts/data/run_symbol_research.sh NVDA
```

## Configuration

Common overrides:

```bash
MARKET_FEED_PYTHON_BIN=python3
MARKET_FEED_TIMEFRAMES=1w,1d,1h,15m
MARKET_FEED_NEWS_LIMIT=5
MARKET_FEED_DIR=state/runs/2026-06-14/market_feed
```

`scripts/lib/common.sh` loads `config/runtime.env` and then `config/runtime.env.local`; environment
variables set in the shell override both files.

## Dry Run

Dry-run market feed uses mock data when routed through the premarket CLI:

```bash
ALLOW_WEEKEND_RUN=1 CODEX_EXEC_DRY_RUN=1 ./scripts/entrypoints/run_premarket.sh
```

Direct market feed collection uses mock data when `CODEX_EXEC_DRY_RUN=1`:

```bash
CODEX_EXEC_DRY_RUN=1 ./scripts/data/run_market_feed_collection.sh
```

## Validation

```bash
python3 -m unittest tests.test_collect_market_feed tests.test_market_context tests.test_technical_signal_schema -v
ALLOW_WEEKEND_RUN=1 CODEX_EXEC_DRY_RUN=1 ./scripts/entrypoints/run_premarket.sh
```

Expected results:

- Unit tests pass.
- `market_feed/manifest.json` is written for the run date.
- Dry-run premarket records stage status in `logs/runs/<date>/pipeline.jsonl`.
