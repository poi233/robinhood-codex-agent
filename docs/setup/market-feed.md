# Market Feed and Technical Research

## Scheduled flow

```bash
./scripts/run_market_feed_collection.sh
./scripts/run_technical_research.sh
```

## Manual flow

```bash
./scripts/run_symbol_research.sh NVDA
```

## Key outputs

- `state/market_feed/<date>/manifest.json`
- `state/technical_signals.json`

## Testing

```bash
python3 -m unittest tests/test_install_repo_skills.py tests/test_collect_market_feed.py tests/test_technical_signal_schema.py -v
ALLOW_WEEKEND_RUN=1 CODEX_EXEC_DRY_RUN=1 ./scripts/run_premarket.sh
```
