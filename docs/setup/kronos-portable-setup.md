# Kronos Portable Setup

## Requirements

- macOS or Linux shell with `bash`
- `git`
- `python3` with Python `venv` support
- Codex installed separately

## Rebuild Steps

```bash
git clone <repo-url>
cd trading
chmod +x scripts/*.sh
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
```

The Task 3 signal-generation and premarket runner commands are pending later tasks. At this commit, `./scripts/verify_kronos_env.sh` only verifies the portable Kronos environment and imports, and only exercises mock signal generation if `scripts/kronos_generate_signals.py` exists.
