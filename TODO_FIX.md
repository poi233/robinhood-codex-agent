# TODO Fix

## 2026-06-16

- [x] Prevent single-symbol or manual technical analysis runs from overwriting the day's global `runtime/state/runs/<date>/signals/technical_signals.json`.
- [x] Keep full-day intraday technical levels available for the intraday policy even when a one-off symbol analysis is generated later in the same day.
- [x] Add a guard or separate output path so manual/symbol-scoped technical runs do not cause `missing_technical_levels` for intraday watchlist candidates.
- [x] Add regression coverage for the case where an ad hoc technical run writes only one symbol and intraday later reads an incomplete technical signal file.

## Context

Today `intraday` was blocked with `missing_technical_levels` even though premarket had completed successfully. The root cause was that an ad hoc `EOSE` technical analysis produced a `technical_signals.json` containing only `EOSE`, which replaced the full-day technical file needed by intraday for symbols such as `MRVL`, `MU`, `AXON`, `EQIX`, and `ANET`.

## Resolution (2026-06-16)

Premarket now writes a **protected full-day snapshot** at `signals/technical_signals.full.json`
(new `RuntimePaths.technical_signals_full_path`, env `TECHNICAL_SIGNALS_FULL_PATH`) every time the
full `run_technical` step completes — on success it mirrors the live file, on a fail-closed branch it
writes the same failed payload to both. Only premarket writes this snapshot; ad hoc / single-symbol
runs touch only the live `technical_signals.json`, which is **not** exposed to the technical Codex
prompt's runtime block as the full path.

Intraday's `load_policy_inputs` now reads the **merge** of the snapshot and the live file via
`signals.technical_fallback.merge_technical_signals(full, live)`: a per-symbol union where the live
file wins for any symbol it contains, but symbols present only in the snapshot are preserved. So an
ad hoc `EOSE` run that clobbers the live file to a single symbol no longer drops `MRVL`/`MU`/etc. for
intraday — and the fresh `EOSE` analysis still flows through. The merge is backward compatible: with
no snapshot it returns the live file unchanged.

Regression coverage: `tests/trading_agent/policy/test_loaders.py`
(`test_intraday_merges_full_snapshot_over_clobbered_technical_live_file`,
`test_intraday_without_snapshot_uses_live_only`) and
`tests/trading_agent/signals/test_technical_merge.py` (5 merge-semantics cases).

## Resolution part 2 — single-symbol output now has its own home (2026-06-16)

Root cause of "I ran a single-symbol analysis and can't find the output": `run_symbol_research.sh`
collected the symbol's **input** market feed into
`runtime/state/runs/<date>/manual/<SYMBOL>/market_feed/`, but the `technical_research` prompt still
wrote its **output** to the *global* `signals/technical_signals.json` (overwriting the full-watchlist
file). So the output wasn't in the `manual/<SYMBOL>/` dir where you'd look for it.

Fix: `src/scripts/data/run_symbol_research.sh` now overrides `TECHNICAL_SIGNALS_PATH` to
`runtime/state/runs/<date>/manual/<SYMBOL>/technical_signals.json` for that one invocation (the same
per-invocation env mechanism the script already uses for `MARKET_FEED_DIR`), and prints
`Symbol research output: <path>` at the end. So now an ad hoc single-symbol run:
- writes its analysis next to its input under `manual/<SYMBOL>/` (findable), and
- never touches the global `signals/technical_signals.json` at all (the clobber is eliminated at the
  source, not just guarded against by the snapshot+merge above).
