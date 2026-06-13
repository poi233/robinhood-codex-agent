# Kronos Portable Setup

## Requirements

- macOS or Linux shell with `bash`
- `git`
- `python3`
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
ALLOW_WEEKEND_RUN=1 KRONOS_USE_MOCK=1 ./scripts/run_kronos_premarket_scan.sh
ALLOW_WEEKEND_RUN=1 KRONOS_USE_MOCK=1 CODEX_EXEC_DRY_RUN=1 ./scripts/run_premarket.sh
```
