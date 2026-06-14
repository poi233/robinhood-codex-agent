# Robinhood Codex Agent

Low-frequency Codex automation for a dedicated Robinhood Agentic Account.

This project is designed to run Codex on a schedule:

- Premarket: research and write today's plan.
- Intraday: check every 30 minutes and optionally act when all gates pass.
- Postmarket: reconcile, summarize, and recommend tomorrow's mode.

Primary runtime entrypoints:

```bash
python3 -m trading_agent premarket
python3 -m trading_agent intraday
python3 -m trading_agent postmarket
```

Default state is deliberately safe:

- `TRADING_MODE=paper`
- `RISK_TIER=0`
- `KILL_SWITCH` exists
- real order placement tools are not auto-approved
- generated logs/state are ignored by git

This is automation infrastructure, not financial advice. Live trading can lose money. Keep this in paper/review mode until the logs are boring and correct.

## Architecture

```text
cron / launchd
  -> scripts/entrypoints/run_*.sh
  -> trading_agent orchestration
  -> account snapshot
  -> market context
  -> parallel advisory scans
  -> candidate snapshots
  -> final planner
  -> archived daily report + logs
```

## Layout

```text
config/
  allowlist.txt          emergency fallback symbols only
  risk.md                human-readable hard risk rules
  risk_tiers.json        machine-readable order caps
  runtime.env            current mode, model, tier, notional caps
  strategy.md            trading and screening strategy
  universe.txt           maximum candidate universe
  dsa_strategy_weights.json
                         Daily Stock Analysis-inspired signal weights

prompts/
  signals/dsa_scan.txt research-only strategy signal generator
  premarket/account_snapshot.txt
                         account, positions, and open-order snapshot
  premarket/market_calendar.txt
                         session calendar and market-status snapshot
  premarket/quote_snapshot_core.txt
                         core market and current-position quotes
  premarket/quote_snapshot_candidates.txt
                         candidate quote snapshot
  premarket/tradability_candidates.txt
                         candidate tradability snapshot
  premarket/catalyst_enrichment.txt
                         candidate news/catalyst enrichment
  premarket/final_research.txt final research-only daily plan generator
  intraday/check.txt     scheduled intraday decision agent
  postmarket/summary.txt review-only daily reconciliation

scripts/
  lib/                   shared shell helpers
  entrypoints/           scheduled lifecycle entrypoints and DSA scan
  data/                  market-feed, technical, and symbol-research runners
  kronos/                Kronos setup, verification, and signal generation
  skills/                repo-owned skill install/verify helpers
  safety/                local safety sanity checks

state/
  .gitkeep               generated runtime state lives here locally
  runs/YYYY-MM-DD/       one folder per trading day
    market_feed/         collected charts, ohlcv, news, manifest
    signals/             dsa, kronos, technical outputs
    planner/             snapshots, allowlist, plan, usage snapshot
    paper/               local paper account, positions, and simulated orders
    archive/             archived premarket report payload

logs/
  .gitkeep               generated runtime logs live here locally
  runs/YYYY-MM-DD/       one folder per trading day
    pipeline.jsonl       stage-level started/completed/failed log
    codex_runs.log       codex stdout aggregation
    errors.log           codex stderr aggregation
    decisions.jsonl      planner and intraday decisions
    orders.jsonl         live/review order audit trail
    postmarket_summary.md

launchd/
  *.plist.example        macOS launchd examples

cron.example             cron schedule example
KILL_SWITCH              default safety stop file
.codex/config.toml       project MCP approval policy
```

`launchd` is the built-in macOS scheduler. In this repo it serves the same role as `cron`: starting `premarket`, `intraday`, and `postmarket` runs on a schedule. Use `launchd` on macOS if you want the jobs managed by LaunchAgents; use `cron` if you prefer a shell-level scheduler.

## Lifecycle

### Premarket

The premarket flow is decomposed so account state is captured once, independent advisory scans run in parallel, and the final planner only synthesizes reviewed snapshots. None of these premarket stages reviews, places, or cancels orders.

First, the account snapshot stage writes `state/runs/<date>/planner/account_snapshot.json`. This is the source of truth for buying power, current positions, and open orders used by later quote, tradability, and final-planner stages.

Then the deterministic market context collector writes `state/runs/<date>/market_feed/` with `charts/`, `ohlcv/`, `news/`, and `manifest.json`.

After that, the first parallel group runs:

- DSA signal scan
- Kronos forecast scan
- repo-owned technical research
- market calendar snapshot
- core quote snapshot for market ETFs and current positions

The optional Daily Stock Analysis-inspired signal layer runs through Codex subscription via `codex exec`.
It does not run the third-party project's own LLM API stack by default.

It:

- reads `config/universe.txt`, `strategy.md`, `risk.md`, and `dsa_strategy_weights.json`
- applies DSA-style lenses: hot theme, event driven, bull trend, shrink pullback, volume breakout, growth quality, and sector leader behavior
- writes `state/runs/<date>/signals/dsa_signals.json`
- appends one `dsa_premarket_scan` record to `logs/runs/<date>/decisions.jsonl`

This layer is advisory only. It can promote, demote, or block research candidates, but it cannot authorize a trade.

The optional Kronos forecast layer runs locally and writes `state/runs/<date>/signals/kronos_signals.json`.
It is advisory only and cannot bypass account, tradability, or risk gates.

The repo-owned technical research layer:

- reads the repo-owned skills under `.agents/skills/`
- writes `state/runs/<date>/signals/technical_signals.json`
- preserves execution-aware price levels, no-trade zones, and long/short-management scenarios for intraday trading

The deterministic candidate merge writes `state/runs/<date>/planner/candidate_snapshot.json` from account holdings/open orders plus advisory outputs.

Then the second parallel group runs only on merged candidates:

- candidate quote snapshot
- candidate tradability snapshot
- catalyst enrichment

Finally, the main premarket agent creates the official daily plan from snapshots instead of re-collecting everything itself.

It:

- reads `config/universe.txt`, `risk.md`, `risk_tiers.json`, `strategy.md`, `runtime.env`, same-day signals, and same-day planner snapshots
- builds a dynamic daily allowlist
- writes `state/runs/<date>/planner/today_allowlist.txt`
- writes `state/runs/<date>/planner/dynamic_allowlist.json`
- writes `state/runs/<date>/planner/daily_plan.json`
- writes `state/runs/<date>/planner/daily_plan.md`
- resets `state/runs/<date>/planner/daily_usage.json`
- appends one `premarket_plan` record to `logs/runs/<date>/decisions.jsonl`
- records stage status in `logs/runs/<date>/pipeline.jsonl`

The screen prioritizes:

- AI semiconductors
- AI data-center infrastructure
- CPO, photonics, and interconnect
- space, defense, drones, satellites, and autonomy
- nuclear, uranium, power, and energy infrastructure
- broad ETFs only when single-name quality is weak or risk is elevated

Run only the DSA signal layer manually:

```bash
./scripts/entrypoints/run_dsa_premarket_scan.sh
```

Disable the DSA signal layer for scheduled premarket runs:

```bash
ENABLE_DSA_SIGNAL_LAYER=0 ./scripts/entrypoints/run_premarket.sh
```

Run the market-feed and technical-research layers manually:

```bash
./scripts/data/run_market_feed_collection.sh
./scripts/data/run_technical_research.sh
./scripts/data/run_symbol_research.sh NVDA
```

### Intraday

The intraday agent is intended to run every 30 minutes during market hours.

It:

- reads the premarket plan and dynamic allowlist
- reads same-day DSA signals when present
- reads same-day `state/runs/<date>/signals/technical_signals.json` when present
- reads same-day planner snapshots such as `account_snapshot.json` and quote snapshots; intraday does not call Robinhood MCP directly
- checks `KILL_SWITCH`
- checks local time window
- checks trading mode
- checks Robinhood account, positions, open orders, order history, and quotes
- enforces daily and single-order caps
- logs exactly one decision per run

Mode behavior:

- `paper`: never calls `review_equity_order` or `place_equity_order`; uses premarket quote snapshots plus local `state/runs/<date>/paper/` ledger to simulate fills
- `review`: may call `review_equity_order`; never places orders
- `live`: may place only after local gates and a clean review pass

### Postmarket

The postmarket agent is review-only.

It:

- reads all state and decision/order logs
- checks Robinhood positions, order history, open orders, and fills
- reconciles local logs with Robinhood
- identifies rule violations or data failures
- reviews allowlist quality
- recommends tomorrow's mode
- writes `logs/runs/<date>/postmarket_summary.md`
- appends one `postmarket_summary` record to `logs/runs/<date>/decisions.jsonl`

## Safety Rules

Hard defaults:

- only the dedicated Robinhood Agentic Account
- only long equities or ETFs
- no options
- no crypto
- no futures
- no margin
- no short selling
- no leveraged or inverse ETFs
- only limit orders
- max single order and daily notional are capped by the most conservative configured value
- if data is missing, stale, or inconsistent, do nothing
- if `KILL_SWITCH` exists, intraday trading is blocked
- DSA signals are advisory only and cannot bypass risk or account checks

Project MCP approval policy:

- read-only Robinhood tools are auto-approved for scheduled `codex exec`
- `review_equity_order` is auto-approved for review-mode simulation
- `place_equity_order`, cancellation, option order tools, and watchlist-write tools remain prompt-gated

## Repo-Owned Trading Skills

This repo now ships its own trading skill pack under `.agents/skills/`.

- install: `./scripts/skills/install_repo_skills.sh`
- verify: `./scripts/skills/verify_repo_skills.sh`
- scheduled collector: `./scripts/data/run_market_feed_collection.sh`
- manual symbol research: `./scripts/data/run_symbol_research.sh NVDA`

The scheduled research workflow now includes:

```text
market_context
  -> parallel: DSA signal scan / Kronos signal scan / technical research
  -> main premarket planner
  -> archive snapshot
```

`planner` is currently the slowest stage because it still performs account checks, quote validation, scoring, and final synthesis inside one Codex run. The pipeline is already parallelized before planner; the next split point is planner decomposition, not the upstream signal layers.

## Setup

Portable Kronos setup requires `git` and a bootstrap interpreter on Python `3.11` or `3.12`.
The setup script prefers `python3.12`, then `python3.11`, and only falls back to `python3` if it resolves to a supported version.
If your machine defaults to an unsupported interpreter such as Python `3.13`, point setup at a compatible one explicitly:

```bash
KRONOS_BOOTSTRAP_PYTHON=$(command -v python3.12) ./scripts/kronos/setup_kronos_env.sh
```

Portable rebuild and validation flow:

```bash
git clone <repo-url>
cd trading
chmod +x scripts/*.sh
./scripts/kronos/setup_kronos_env.sh
./scripts/kronos/verify_kronos_env.sh
./scripts/safety/check_safety.sh
ALLOW_WEEKEND_RUN=1 KRONOS_USE_MOCK=1 ./scripts/kronos/run_kronos_premarket_scan.sh
ALLOW_WEEKEND_RUN=1 CODEX_EXEC_DRY_RUN=1 ./scripts/entrypoints/run_premarket.sh
```

For a clean rebuild of the portable Kronos environment:

```bash
rm -rf .venv-kronos .vendor/kronos
./scripts/kronos/setup_kronos_env.sh
./scripts/kronos/verify_kronos_env.sh
```

Install and authenticate Codex, then connect Robinhood Trading MCP:

```bash
codex login
codex mcp add robinhood-trading --url https://agent.robinhood.com/mcp/trading
codex
/mcp
```

Complete Robinhood Agentic Account authentication on desktop.

## Dry Run

Dry-run the shell layer without invoking Codex after setup and safety checks pass:

```bash
CODEX_EXEC_DRY_RUN=1 ./scripts/entrypoints/run_premarket.sh
CODEX_EXEC_DRY_RUN=1 ./scripts/entrypoints/run_intraday.sh
CODEX_EXEC_DRY_RUN=1 ./scripts/entrypoints/run_postmarket.sh
```

Because `KILL_SWITCH` exists by default, intraday should skip safely.

For a live-data premarket run without order placement, leave `CODEX_EXEC_DRY_RUN` unset:

```bash
ALLOW_WEEKEND_RUN=1 ./scripts/entrypoints/run_premarket.sh
```

## Paper Test

Run a full local paper test:

```bash
ALLOW_OUTSIDE_MARKET_TEST=1 ./scripts/entrypoints/run_all_paper_once.sh
```

In paper mode the agent must not call order review or order placement tools.

## Schedule

Times are America/Los_Angeles:

- `05:30` premarket research
- `06:45` first intraday check
- every 30 minutes until `12:45`
- `13:10` postmarket summary

Use `cron.example` or the `launchd/*.plist.example` files after replacing `__REPO_ROOT__` with your local repository path.

## Portability Notes

- `README.md` is the source of truth for setup and runtime usage.
- `docs/` is intentionally local-only and should not be committed or uploaded.
- Machine-specific values belong in `config/runtime.env.local`, which is git-ignored.
- Scheduler examples use placeholders and must be customized locally.

## Rollout

Recommended rollout:

1. Paper only: inspect `would_trade` and `no_action` decisions.
2. Review only: allow `review_equity_order`, never place.
3. Live tier 0: keep `RISK_TIER=0`, small notional only.
4. Raise tiers manually only after clean postmarket summaries.

Never let Codex edit `RISK_TIER` by itself. Postmarket may recommend a tier change, but the human changes it.

## Generated Files

These are intentionally ignored by git:

- `state/runs/YYYY-MM-DD/market_feed/`
- `state/runs/YYYY-MM-DD/signals/`
- `state/runs/YYYY-MM-DD/planner/`
- `state/runs/YYYY-MM-DD/archive/`
- `logs/runs/YYYY-MM-DD/`

Keep generated state and logs local because they can contain account size, decisions, symbols, timestamps, and operational details.
