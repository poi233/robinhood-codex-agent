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
CODEX_EXEC_DRY_RUN=1 ./scripts/run_premarket.sh
```

The Task 3 signal-generation and premarket runner commands are pending later tasks. At this commit, `./scripts/verify_kronos_env.sh` only verifies the portable Kronos environment and imports, and only exercises mock signal generation if `scripts/kronos_generate_signals.py` exists.
