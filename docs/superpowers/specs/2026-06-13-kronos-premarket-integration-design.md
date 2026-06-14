# Kronos Premarket Portable Integration Design

Date: 2026-06-13
Repo: `/Users/puyihao/Documents/trading`
Status: Updated for portable multi-machine setup

## Goal

Integrate Kronos into the existing Robinhood Codex trading system as a premarket research input for deep analysis, while also making the setup reproducible on a new machine from the remote repository plus documented manual authentication steps.

Kronos should improve candidate ranking and setup bias selection during premarket planning, while all existing risk, account, tradability, and execution gates remain authoritative.

## Primary Requirements

1. Kronos is used only in premarket research.
2. Kronos remains advisory and non-blocking at runtime.
3. A new machine can clone this repository and reproduce the Kronos environment using repository-owned setup and verification scripts.
4. Machine-specific paths and local credentials do not enter git.
5. Codex login, Robinhood MCP registration, and Robinhood account authentication remain explicit manual steps.

## Non-Goals

- No direct Kronos dependency in intraday execution or order placement
- No automatic order decisions based solely on Kronos output
- No first-pass service or API deployment for Kronos
- No Kronos training or fine-tuning in the first implementation
- No attempt to fully automate Codex login or Robinhood account authentication

## Recommended Approach

Three integration patterns were considered for Kronos itself:

1. Add Kronos as a separate premarket signal layer that writes a local state file.
2. Embed Kronos inference directly inside the main premarket prompt.
3. Run Kronos manually outside the automation flow and paste results into the system.

Recommended: option 1, implemented so the resulting signal file is consumed by the existing main premarket research layer.

Three portability patterns were also considered:

1. Add Kronos as a git submodule.
2. Let repository setup scripts clone a fixed Kronos commit into a repository-owned vendor directory.
3. Depend only on package installation without cloning Kronos source.

Recommended: portability option 2.

Why:

- preserves current system boundaries
- keeps failures isolated and observable
- fits the repository's shell entrypoint plus local state file architecture
- avoids turning the main premarket prompt into an inference runtime
- keeps the main repository clean while still allowing deterministic, scriptable setup
- avoids path drift by using repository-owned install locations

## Architecture

The premarket flow will become:

```text
src/config/universe.txt
  -> DSA signal scan
  -> Kronos signal scan
  -> main premarket research
  -> daily plan and dynamic allowlist
```

Execution boundary remains unchanged:

- `src/scripts/entrypoints/run_premarket.sh` orchestrates the research pipeline
- `src/scripts/entrypoints/run_intraday.sh` and downstream order logic do not invoke Kronos
- Kronos is advisory only, similar to the DSA layer, but focused on forecast path and setup bias

Portable environment boundary:

- repository-owned Kronos checkout lives under `.vendor/kronos`
- repository-owned Python environment lives under `.venv-kronos`
- machine-local overrides live in `src/config/runtime.env.local`
- repository defaults remain in `src/config/runtime.env`

## New Components

### 1. `src/scripts/kronos/run_kronos_premarket_scan.sh`

Shell entrypoint for the Kronos signal layer.

Responsibilities:

- load shared runtime from `src/scripts/lib/common.sh`
- read feature flags from `src/config/runtime.env` and `src/config/runtime.env.local`
- prepare the candidate list from `src/config/universe.txt`
- invoke local Python inference
- write `runtime/state/runs/<date>/signals/kronos_signals.json`
- log failures without aborting the whole premarket run

### 2. `src/scripts/kronos/kronos_generate_signals.py`

Local Python inference wrapper.

Responsibilities:

- read the selected universe
- obtain or load recent OHLCV data required by Kronos
- run inference using a configured local Kronos model
- normalize model output into the repository signal schema
- emit a single JSON artifact for downstream consumption

This script is inference-only in the first iteration.

### 3. `runtime/state/runs/<date>/signals/kronos_signals.json`

Daily advisory output from Kronos for premarket consumption.

Suggested schema:

```json
{
  "date": "YYYY-MM-DD",
  "generated_at": "ISO-8601 timestamp with timezone",
  "timeframe": "30m|1h|1d",
  "horizon_bars": 8,
  "source_universe": "src/config/universe.txt",
  "model": {
    "name": "NeoQuasar/Kronos-small",
    "mode": "inference_only"
  },
  "data_status": "ok|partial|failed|stale",
  "symbols": {
    "NVDA": {
      "direction_bias": "bullish|bearish|neutral",
      "confidence": 0.72,
      "predicted_return_bps": 180,
      "predicted_volatility_bps": 260,
      "path_summary": "up_then_consolidate",
      "setup_bias": "breakout|pullback|chop|avoid",
      "risk_flags": ["high_gap_risk"],
      "reason": "short text"
    }
  },
  "notes": "short text"
}
```

### 4. `src/prompts/premarket/final_research.txt`

The existing premarket prompt will be extended to:

- read `runtime/state/runs/<date>/signals/kronos_signals.json` if present and current
- treat Kronos as an advisory forecast layer
- use Kronos only for candidate ranking, setup bias, and watch or block context
- record Kronos availability inside plan data status

No separate Codex prompt is required for the first Kronos implementation if the Python script emits normalized JSON directly.

### 5. `src/scripts/kronos/setup_kronos_env.sh`

Portable environment bootstrap script.

Responsibilities:

- verify `git`, `python3`, and `pip` availability
- create `.venv-kronos`
- clone Kronos into `.vendor/kronos`
- checkout a fixed commit
- install upstream Kronos requirements plus repository-specific extras
- create `src/config/runtime.env.local` from `src/config/runtime.env.local.example` when missing
- populate local machine paths for `KRONOS_PYTHON_BIN` and `KRONOS_PROJECT_ROOT`
- fail fast on install errors

### 6. `src/scripts/kronos/verify_kronos_env.sh`

Portable environment verification script.

Responsibilities:

- verify that `KRONOS_PYTHON_BIN` exists
- verify that `KRONOS_PROJECT_ROOT` exists
- verify that Python imports `pandas`, `yfinance`, `torch`, and Kronos classes
- verify that the generator can run in mock mode
- print a clear pass/fail summary for operators

### 7. `src/config/runtime.env.local.example`

Local override template for machine-specific values.

Responsibilities:

- document local-only overrides
- keep absolute paths out of committed defaults
- provide a predictable starting point for new machines

### 8. `docs/setup/kronos-portable-setup.md`

Detailed machine-rebuild guide.

Responsibilities:

- document clone, bootstrap, verify, and authentication steps
- separate fully automatable setup from required manual account/auth work
- define acceptance criteria for a successful rebuild

### 9. `requirements-kronos-extra.txt`

Repository-specific Python additions layered on top of upstream Kronos requirements.

Expected contents:

- `yfinance`
- any other small dependencies needed only by this repository's integration layer

## Portable Directory Layout

Expected repository-local layout after setup:

```text
.vendor/
  kronos/                fixed-commit upstream checkout

.venv-kronos/            repository-owned Python environment

src/config/
  runtime.env            committed repository defaults
  runtime.env.local      machine-local overrides, gitignored
  runtime.env.local.example
```

`.vendor/kronos` and `.venv-kronos` are local build/runtime artifacts and should remain out of git.

## Runtime Configuration

Committed defaults belong in `src/config/runtime.env`, for example:

```bash
ENABLE_KRONOS_SIGNAL_LAYER=1
KRONOS_MODEL_NAME=NeoQuasar/Kronos-small
KRONOS_TOKENIZER_NAME=NeoQuasar/Kronos-Tokenizer-base
KRONOS_TIMEFRAME=30m
KRONOS_HORIZON_BARS=8
KRONOS_MIN_CONFIDENCE=0.60
```

Machine-local values belong in `src/config/runtime.env.local`, for example:

```bash
KRONOS_PYTHON_BIN=/abs/path/to/repo/.venv-kronos/bin/python
KRONOS_PROJECT_ROOT=/abs/path/to/repo/.vendor/kronos
```

These values influence research behavior only. They must not override risk caps or execution permissions.

## Version Locking

Portable setup must lock the following:

- Kronos repository URL
- Kronos commit SHA
- Python version expectation
- repository-specific extra dependencies

Recommended setup script constants:

```bash
KRONOS_REPO_URL="https://github.com/shiyu-coder/Kronos.git"
KRONOS_COMMIT_SHA="67b630e67f6a18c9e9be918d9b4337c960db1e9a"
PYTHON_MIN_VERSION="3.11"
```

The setup script must check out the fixed Kronos commit rather than tracking a floating branch.

## Integration Rules

Kronos must obey the following constraints:

- it cannot introduce symbols outside `src/config/universe.txt`
- it cannot override `src/config/risk.md` or `src/config/risk_tiers.json`
- it cannot bypass Robinhood tradability, buying power, open-order, or account identification checks
- it cannot widen `max_daily_notional` or `max_single_order_notional`
- it cannot directly select order actions
- it cannot become the sole basis for a trade candidate

If Kronos and DSA disagree, the main premarket research layer remains the final adjudicator.

## Failure Handling

Installation behavior and runtime behavior are intentionally different.

### Installation phase

Installation must fail fast if any of the following occur:

- Kronos clone fails
- fixed commit checkout fails
- virtual environment creation fails
- dependency installation fails
- local runtime file generation fails
- verification import checks fail

Portable setup should never silently degrade during installation.

### Runtime phase

The Kronos layer is non-blocking.

Expected behavior:

- if `run_kronos_premarket_scan.sh` fails, `src/scripts/entrypoints/run_premarket.sh` logs the failure and continues
- if `runtime/state/runs/<date>/signals/kronos_signals.json` is missing, stale, partial, or invalid, main premarket research still runs
- if Kronos data is unusable, the final daily plan records that status explicitly
- no Kronos failure may relax any safety gate

This mirrors the existing DSA signal layer behavior and keeps research degradation separate from execution safety.

## Data Flow

1. Operator clones the repository.
2. `src/scripts/kronos/setup_kronos_env.sh` creates `.venv-kronos`, clones `.vendor/kronos`, installs dependencies, and writes local env overrides.
3. `src/scripts/kronos/verify_kronos_env.sh` validates the environment.
4. Operator manually completes Codex login, Robinhood MCP setup, and Robinhood desktop authentication.
5. `src/scripts/entrypoints/run_premarket.sh` starts.
6. `dsa_premarket_scan` runs if enabled.
7. `kronos_premarket_scan` runs if enabled.
8. `src/scripts/kronos/kronos_generate_signals.py` writes `runtime/state/runs/<date>/signals/kronos_signals.json`.
9. `src/prompts/premarket/final_research.txt` reads DSA and Kronos signal files when available.
10. Main premarket research produces:
   - `runtime/state/today_allowlist.txt`
   - `runtime/state/dynamic_allowlist.json`
   - `runtime/state/daily_plan.json`
   - `runtime/state/daily_plan.md`

## Machine-Rebuild Workflow

The documented rebuild flow for a new machine should be:

```bash
git clone <repo-url>
cd trading
chmod +x src/scripts/*.sh
./src/scripts/kronos/setup_kronos_env.sh
./src/scripts/kronos/verify_kronos_env.sh
```

Then the required manual steps:

```bash
codex login
codex mcp add robinhood-trading --url https://agent.robinhood.com/mcp/trading
codex
/mcp
```

Then validation:

```bash
./src/scripts/safety/check_safety.sh
ALLOW_WEEKEND_RUN=1 KRONOS_USE_MOCK=1 ./src/scripts/kronos/run_kronos_premarket_scan.sh
ALLOW_WEEKEND_RUN=1 KRONOS_USE_MOCK=1 CODEX_EXEC_DRY_RUN=1 ./src/scripts/entrypoints/run_premarket.sh
```

## Testing Strategy

Testing should be staged to isolate integration risk.

### Phase 1: Contract validation

- verify `runtime/state/runs/<date>/signals/kronos_signals.json` is always valid JSON
- verify required top-level fields exist
- verify symbols not in the universe are rejected

### Phase 2: Portable bootstrap validation

- verify setup script creates `.venv-kronos`
- verify setup script clones `.vendor/kronos` at the locked commit
- verify local env file is created without overwriting an existing operator-customized file
- verify verify script can import all required modules and Kronos classes

### Phase 3: Pipeline validation

- run a dry run of premarket flow
- verify execution order is DSA, then Kronos, then main premarket research
- verify Kronos failure does not stop daily plan generation

### Phase 4: Decision-boundary validation

- verify Kronos affects ranking, setup bias, and watch or block context only
- verify Kronos cannot change tier caps, allowed actions, or account safety behavior
- compare representative symbols to ensure outputs are interpretable

## Implementation Order

1. Add local config layering support to shared shell runtime.
2. Add portable setup files and `.gitignore` updates.
3. Add `setup_kronos_env.sh` and `verify_kronos_env.sh`.
4. Add `src/scripts/kronos/kronos_generate_signals.py` with mock output first.
5. Add `src/scripts/kronos/run_kronos_premarket_scan.sh`.
6. Update `src/scripts/entrypoints/run_premarket.sh` to call the Kronos layer after DSA and before main premarket research.
7. Update `src/prompts/premarket/final_research.txt` to read and constrain Kronos signals.
8. Update `README.md`, setup docs, and `src/scripts/safety/check_safety.sh`.
9. Validate bootstrap, mock flow, and dry-run behavior.
10. Replace mock-only inference with real Kronos model loading once the integration contract is stable.

## Risks and Tradeoffs

- Embedding Kronos directly into the main prompt would reduce files but mix inference and decision logic in one place.
- Service deployment would make future scaling easier but adds process, timeout, and health-check complexity that is not justified for a low-frequency premarket batch job.
- A vendor checkout created by setup is slightly slower on first install than a submodule, but keeps the main repository cleaner and avoids submodule workflow friction.
- Full-market scanning may be too slow or noisy in the first version; the initial design assumes a bounded universe and moderate batch size.

## Acceptance Criteria

The design is successful when:

- Kronos is integrated into premarket only
- the main premarket flow can consume Kronos output without depending on it for availability
- daily plans record Kronos signal status explicitly
- all existing safety and execution boundaries remain unchanged
- the repository can be cloned on a new machine and rebuilt with repository-owned setup and verification scripts
- local machine paths and credentials remain out of git
- mock mode and dry run work before Robinhood authentication is completed
- after manual authentication, the premarket pipeline can consume Kronos signals without changing execution boundaries
