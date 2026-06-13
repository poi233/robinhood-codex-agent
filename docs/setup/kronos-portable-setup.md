# Kronos Portable Setup

## Requirements

- macOS or Linux shell with `bash`
- `git`
- Python `3.11` or `3.12` with Python `venv` support
- Codex installed separately

`./scripts/setup_kronos_env.sh` prefers `python3.12`, then `python3.11`.
If your default `python3` is unsupported, set `KRONOS_BOOTSTRAP_PYTHON` explicitly:

```bash
KRONOS_BOOTSTRAP_PYTHON=$(command -v python3.12) ./scripts/setup_kronos_env.sh
```

## Rebuild Steps

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

## Manual Authentication Steps

```bash
codex login
codex mcp add robinhood-trading --url https://agent.robinhood.com/mcp/trading
codex
/mcp
```

Complete Robinhood Agentic Account authentication on desktop.

## Validation

```bash
./scripts/check_safety.sh
ALLOW_WEEKEND_RUN=1 KRONOS_USE_MOCK=1 ./scripts/run_kronos_premarket_scan.sh
ALLOW_WEEKEND_RUN=1 KRONOS_USE_MOCK=1 CODEX_EXEC_DRY_RUN=1 ./scripts/run_premarket.sh
```

Expected results:

- `./scripts/check_safety.sh` reports portable Kronos setup files and premarket wiring as `ok`
- `./scripts/run_kronos_premarket_scan.sh` writes `state/kronos_signals.json`
- `./scripts/run_premarket.sh` continues in dry-run mode and appends DSA, Kronos, and premarket entries to `logs/codex_runs.log`
