# Kronos Premarket Integration Design

Date: 2026-06-13
Repo: `/Users/puyihao/Documents/trading`
Status: Draft approved in conversation, written for user review

## Goal

Integrate Kronos into the existing Robinhood Codex trading system as a premarket research input for deep analysis without changing the execution boundary. Kronos should improve candidate ranking and setup bias selection during premarket planning, while all existing risk, account, and tradability gates remain authoritative.

## Non-Goals

- No direct Kronos dependency in intraday execution or order placement
- No automatic order decisions based solely on Kronos output
- No first-pass service or API deployment for Kronos
- No Kronos training or fine-tuning in the first implementation

## Recommended Approach

Three integration patterns were considered:

1. Add Kronos as a separate premarket signal layer that writes a local state file.
2. Embed Kronos inference directly inside the main premarket prompt.
3. Run Kronos manually outside the automation flow and paste results into the system.

Recommended: option 1, implemented so the resulting signal file is consumed by the existing main premarket research layer.

Why:

- preserves current system boundaries
- keeps failures isolated and observable
- fits the repository's shell entrypoint plus local state file architecture
- avoids turning the main premarket prompt into an inference runtime

## Architecture

The premarket flow will become:

```text
config/universe.txt
  -> DSA signal scan
  -> Kronos signal scan
  -> main premarket research
  -> daily plan and dynamic allowlist
```

Execution boundary remains unchanged:

- `scripts/run_premarket.sh` orchestrates the research pipeline
- `scripts/run_intraday.sh` and downstream order logic do not invoke Kronos
- Kronos is advisory only, similar to the DSA layer, but focused on forecast path and setup bias

## New Components

### 1. `scripts/run_kronos_premarket_scan.sh`

Shell entrypoint for the Kronos signal layer.

Responsibilities:

- load shared runtime from `scripts/common.sh`
- read feature flags from `config/runtime.env`
- prepare the candidate list from `config/universe.txt`
- invoke local Python inference
- write `state/kronos_signals.json`
- log failures without aborting the whole premarket run

### 2. `scripts/kronos_generate_signals.py`

Local Python inference wrapper.

Responsibilities:

- read the selected universe
- obtain or load recent OHLCV data required by Kronos
- run inference using a configured local Kronos model
- normalize model output into the repository signal schema
- emit a single JSON artifact for downstream consumption

This script should be inference-only in the first iteration.

### 3. `state/kronos_signals.json`

Daily advisory output from Kronos for premarket consumption.

Suggested schema:

```json
{
  "date": "YYYY-MM-DD",
  "generated_at": "ISO-8601 timestamp with timezone",
  "timeframe": "30m|1h|1d",
  "horizon_bars": 8,
  "source_universe": "config/universe.txt",
  "model": {
    "name": "kronos-small",
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

### 4. `prompts/premarket_research.txt`

The existing premarket prompt will be extended to:

- read `state/kronos_signals.json` if present and current
- treat Kronos as an advisory forecast layer
- use Kronos only for candidate ranking, setup bias, and watch or block context
- record Kronos availability inside plan data status

No separate Codex prompt is required for the first Kronos implementation if the Python script emits the normalized JSON directly.

## Runtime Configuration

The following settings should be added to `config/runtime.env`:

```bash
ENABLE_KRONOS_SIGNAL_LAYER=1
KRONOS_TIMEFRAME=30m
KRONOS_HORIZON_BARS=8
KRONOS_MODEL_NAME=kronos-small
KRONOS_MIN_CONFIDENCE=0.60
```

These values should only influence research behavior. They must not override risk caps or execution permissions.

## Integration Rules

Kronos must obey the following constraints:

- it cannot introduce symbols outside `config/universe.txt`
- it cannot override `config/risk.md` or `config/risk_tiers.json`
- it cannot bypass Robinhood tradability, buying power, open-order, or account identification checks
- it cannot widen `max_daily_notional` or `max_single_order_notional`
- it cannot directly select order actions
- it cannot become the sole basis for a trade candidate

If Kronos and DSA disagree, the main premarket research layer remains the final adjudicator.

## Failure Handling

The Kronos layer is non-blocking.

Expected behavior:

- if `run_kronos_premarket_scan.sh` fails, `scripts/run_premarket.sh` logs the failure and continues
- if `state/kronos_signals.json` is missing, stale, partial, or invalid, main premarket research still runs
- if Kronos data is unusable, the final daily plan records that status explicitly
- no Kronos failure may relax any safety gate

This mirrors the existing DSA signal layer behavior and keeps research degradation separate from execution safety.

## Data Flow

1. `scripts/run_premarket.sh` starts.
2. `dsa_premarket_scan` runs if enabled.
3. `kronos_premarket_scan` runs if enabled.
4. `scripts/kronos_generate_signals.py` writes `state/kronos_signals.json`.
5. `prompts/premarket_research.txt` reads DSA and Kronos signal files when available.
6. Main premarket research produces:
   - `state/today_allowlist.txt`
   - `state/dynamic_allowlist.json`
   - `state/daily_plan.json`
   - `state/daily_plan.md`

## Testing Strategy

Testing should be staged to isolate integration risk.

### Phase 1: Contract validation

- verify `state/kronos_signals.json` is always valid JSON
- verify required top-level fields exist
- verify symbols not in the universe are rejected

### Phase 2: Pipeline validation

- run a dry run of premarket flow
- verify execution order is DSA, then Kronos, then main premarket research
- verify Kronos failure does not stop daily plan generation

### Phase 3: Decision-boundary validation

- verify Kronos affects ranking, setup bias, and watch or block context only
- verify Kronos cannot change tier caps, allowed actions, or account safety behavior
- compare a few representative symbols to ensure outputs are interpretable

## Implementation Order

1. Add `ENABLE_KRONOS_SIGNAL_LAYER` and related runtime config.
2. Create `scripts/kronos_generate_signals.py` with mock or placeholder output first.
3. Create `scripts/run_kronos_premarket_scan.sh`.
4. Update `scripts/run_premarket.sh` to call the Kronos layer after DSA and before main premarket research.
5. Update `prompts/premarket_research.txt` to read and constrain Kronos signals.
6. Validate in dry run and paper mode.
7. Replace placeholder output with real Kronos inference once the integration contract is stable.

## Risks and Tradeoffs

- Embedding Kronos directly into the main prompt would reduce files but mix inference and decision logic in one place.
- Service deployment would make future scaling easier but adds process, timeout, and health-check complexity that is not justified for a low-frequency premarket batch job.
- Full-market scanning may be too slow or noisy in the first version; the initial design assumes a bounded universe and moderate batch size.

## Acceptance Criteria

The design is successful when:

- Kronos is integrated into premarket only
- the main premarket flow can consume Kronos output without depending on it for availability
- daily plans record Kronos signal status explicitly
- all existing safety and execution boundaries remain unchanged
- the system can be validated in dry run and paper mode before real signal usage
