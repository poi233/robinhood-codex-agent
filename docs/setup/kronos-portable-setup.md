# Kronos Portable Setup

Kronos is an advisory premarket signal layer. It writes
`runtime/state/runs/<date>/signals/kronos_signals.json` and cannot authorize a trade by itself.

## Requirements

- macOS or Linux shell with `bash`
- `git`
- Python `3.11` or `3.12` with `venv` support
- network access for the first setup run
- Codex and Robinhood MCP setup handled separately

The setup script creates:

- `.vendor/kronos/`
- `.venv-kronos/`
- `src/config/runtime.env.local` entries for `KRONOS_PYTHON_BIN` and `KRONOS_PROJECT_ROOT`

## Model Selection

The default model is `NeoQuasar/Kronos-base`, paired with
`NeoQuasar/Kronos-Tokenizer-base`. This is the best public Kronos checkpoint currently usable by the
repo. `Kronos-large` is not selected because upstream marks it as not publicly available.

Defaults:

```bash
KRONOS_MODEL_NAME=NeoQuasar/Kronos-base
KRONOS_TOKENIZER_NAME=NeoQuasar/Kronos-Tokenizer-base
KRONOS_LOOKBACK_BARS=512
```

Keep `KRONOS_LOOKBACK_BARS` at or below `512` for `Kronos-small` and `Kronos-base`; the predictor
uses a 512-bar max context for those checkpoints.

## Install

```bash
./src/scripts/kronos/setup_kronos_env.sh
./src/scripts/kronos/verify_kronos_env.sh
```

If your default `python3` is unsupported, point setup at a compatible interpreter:

```bash
KRONOS_BOOTSTRAP_PYTHON=$(command -v python3.12) ./src/scripts/kronos/setup_kronos_env.sh
```

The script prefers `python3.12`, then `python3.11`, and only falls back to `python3` if it is a
supported version.

## Clean Rebuild

```bash
rm -rf .venv-kronos .vendor/kronos
./src/scripts/kronos/setup_kronos_env.sh
./src/scripts/kronos/verify_kronos_env.sh
```

## Run Manually

Mock signal generation:

```bash
ALLOW_WEEKEND_RUN=1 KRONOS_USE_MOCK=1 ./src/scripts/kronos/run_kronos_premarket_scan.sh
```

Live signal generation:

```bash
ALLOW_WEEKEND_RUN=1 ./src/scripts/kronos/run_kronos_premarket_scan.sh
```

Expected output:

```text
runtime/state/runs/<date>/signals/kronos_signals.json
```

## Premarket Integration

Premarket runs Kronos through `trading_agent/orchestration/premarket.py` when
`ENABLE_KRONOS_SIGNAL_LAYER=1`.

Disable it for a run:

```bash
ENABLE_KRONOS_SIGNAL_LAYER=0 ./src/scripts/entrypoints/run_premarket.sh
```

Dry-run the full premarket pipeline without invoking Codex prompts:

```bash
ALLOW_WEEKEND_RUN=1 KRONOS_USE_MOCK=1 CODEX_EXEC_DRY_RUN=1 ./src/scripts/entrypoints/run_premarket.sh
```

## Validation

```bash
./src/scripts/kronos/verify_kronos_env.sh
./src/scripts/safety/check_safety.sh
python3 -m unittest tests.test_kronos_generate_signals -v
```

Expected results:

- `verify_kronos_env.sh` prints `Kronos portable verification passed.`
- `check_safety.sh` reports Kronos setup and premarket wiring as `ok`.
- Tests pass, with no live network test required unless explicitly enabled.
