# Robinhood Codex Agent

Low-frequency Codex automation for a dedicated Robinhood Agentic Account.

This project is designed to run Codex on a schedule:

- Premarket: research and write today's plan.
- Intraday: check every 30 minutes and optionally act when all gates pass.
- Postmarket: reconcile, summarize, and recommend tomorrow's mode.

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
  -> scripts/run_*.sh
  -> codex exec
  -> Codex as MCP client
  -> Robinhood Trading MCP
  -> Robinhood Agentic Account
  -> local state + logs
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
  dsa_premarket_scan.txt research-only strategy signal generator
  premarket_research.txt research-only daily plan generator
  intraday_check.txt     scheduled intraday decision agent
  postmarket_summary.txt review-only daily reconciliation

scripts/
  common.sh              shared runtime helpers
  run_dsa_premarket_scan.sh
                         optional standalone DSA signal scan
  run_premarket.sh       premarket entrypoint
  run_intraday.sh        intraday entrypoint
  run_postmarket.sh      postmarket entrypoint
  run_all_paper_once.sh  manual full paper test
  check_safety.sh        local safety sanity check

state/
  .gitkeep               generated plans live here locally

logs/
  .gitkeep               generated logs live here locally

launchd/
  *.plist.example        macOS launchd examples

cron.example             cron schedule example
KILL_SWITCH              default safety stop file
.codex/config.toml       project MCP approval policy
```

## Lifecycle

### Premarket

The premarket flow has two research-only layers. Neither reviews, places, or cancels orders.

First, the optional Daily Stock Analysis-inspired signal layer runs through Codex subscription via `codex exec`.
It does not run the third-party project's own LLM API stack by default.

It:

- reads `config/universe.txt`, `strategy.md`, `risk.md`, and `dsa_strategy_weights.json`
- applies DSA-style lenses: hot theme, event driven, bull trend, shrink pullback, volume breakout, growth quality, and sector leader behavior
- writes `state/dsa_signals.json`
- appends one `dsa_premarket_scan` record to `logs/decisions.jsonl`

This layer is advisory only. It can promote, demote, or block research candidates, but it cannot authorize a trade.

Then the main premarket agent creates the official daily plan.

It:

- reads `config/universe.txt`, `risk.md`, `risk_tiers.json`, `strategy.md`, `runtime.env`, and same-day `state/dsa_signals.json` when present
- identifies the dedicated Robinhood Agentic Account
- checks buying power, positions, and open equity orders
- scans market regime and priority sectors
- builds a dynamic daily allowlist
- writes `state/today_allowlist.txt`
- writes `state/dynamic_allowlist.json`
- writes `state/daily_plan.json`
- writes `state/daily_plan.md`
- resets `state/daily_usage.json`
- appends one `premarket_plan` record to `logs/decisions.jsonl`

The screen prioritizes:

- AI semiconductors
- AI data-center infrastructure
- CPO, photonics, and interconnect
- space, defense, drones, satellites, and autonomy
- nuclear, uranium, power, and energy infrastructure
- broad ETFs only when single-name quality is weak or risk is elevated

Run only the DSA signal layer manually:

```bash
./scripts/run_dsa_premarket_scan.sh
```

Disable the DSA signal layer for scheduled premarket runs:

```bash
ENABLE_DSA_SIGNAL_LAYER=0 ./scripts/run_premarket.sh
```

### Intraday

The intraday agent is intended to run every 30 minutes during market hours.

It:

- reads the premarket plan and dynamic allowlist
- reads same-day DSA signals when present
- checks `KILL_SWITCH`
- checks local time window
- checks trading mode
- checks Robinhood account, positions, open orders, order history, and quotes
- enforces daily and single-order caps
- logs exactly one decision per run

Mode behavior:

- `paper`: never calls `review_equity_order` or `place_equity_order`; logs `no_action` or `would_trade`
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
- writes `logs/postmarket_summary.md`
- appends one `postmarket_summary` record to `logs/decisions.jsonl`

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

## Setup

Portable Kronos setup requires `git` and a bootstrap interpreter on Python `3.11` or `3.12`.
The setup script prefers `python3.12`, then `python3.11`, and only falls back to `python3` if it resolves to a supported version.
If your machine defaults to an unsupported interpreter such as Python `3.13`, point setup at a compatible one explicitly:

```bash
KRONOS_BOOTSTRAP_PYTHON=$(command -v python3.12) ./scripts/setup_kronos_env.sh
```

Portable rebuild and validation flow:

```bash
git clone <repo-url>
cd trading
chmod +x scripts/*.sh
./scripts/setup_kronos_env.sh
./scripts/verify_kronos_env.sh
./scripts/check_safety.sh
```

For a clean rebuild of the portable Kronos environment:

```bash
rm -rf .venv-kronos .vendor/kronos
./scripts/setup_kronos_env.sh
./scripts/verify_kronos_env.sh
```

Install and authenticate Codex, then connect Robinhood Trading MCP:

```bash
codex login
codex mcp add robinhood-trading --url https://agent.robinhood.com/mcp/trading
codex
/mcp
```

Complete Robinhood Agentic Account authentication on desktop.

Then run:

```bash
cd /path/to/robinhood-codex-agent
chmod +x scripts/*.sh
./scripts/setup_kronos_env.sh
./scripts/verify_kronos_env.sh
./scripts/check_safety.sh
```

## Dry Run

Dry-run the shell layer without invoking Codex after setup and safety checks pass:

```bash
CODEX_EXEC_DRY_RUN=1 ./scripts/run_premarket.sh
CODEX_EXEC_DRY_RUN=1 ./scripts/run_intraday.sh
CODEX_EXEC_DRY_RUN=1 ./scripts/run_postmarket.sh
```

Because `KILL_SWITCH` exists by default, intraday should skip safely.

## Paper Test

Run a full local paper test:

```bash
ALLOW_OUTSIDE_MARKET_TEST=1 ./scripts/run_all_paper_once.sh
```

In paper mode the agent must not call order review or order placement tools.

## Schedule

Times are America/Los_Angeles:

- `05:30` premarket research
- `06:45` first intraday check
- every 30 minutes until `12:45`
- `13:10` postmarket summary

Use `cron.example` or the `launchd/*.plist.example` files.

## Rollout

Recommended rollout:

1. Paper only: inspect `would_trade` and `no_action` decisions.
2. Review only: allow `review_equity_order`, never place.
3. Live tier 0: keep `RISK_TIER=0`, small notional only.
4. Raise tiers manually only after clean postmarket summaries.

Never let Codex edit `RISK_TIER` by itself. Postmarket may recommend a tier change, but the human changes it.

## Generated Files

These are intentionally ignored by git:

- `state/daily_plan.json`
- `state/daily_plan.md`
- `state/dynamic_allowlist.json`
- `state/dsa_signals.json`
- `state/today_allowlist.txt`
- `state/daily_usage.json`
- `logs/codex_runs.log`
- `logs/decisions.jsonl`
- `logs/orders.jsonl`
- `logs/errors.log`
- `logs/postmarket_summary.md`

Keep generated state and logs local because they can contain account size, decisions, symbols, timestamps, and operational details.
