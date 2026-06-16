# TODO Fix

## 2026-06-16

- [ ] Prevent single-symbol or manual technical analysis runs from overwriting the day's global `runtime/state/runs/<date>/signals/technical_signals.json`.
- [ ] Keep full-day intraday technical levels available for the intraday policy even when a one-off symbol analysis is generated later in the same day.
- [ ] Add a guard or separate output path so manual/symbol-scoped technical runs do not cause `missing_technical_levels` for intraday watchlist candidates.
- [ ] Add regression coverage for the case where an ad hoc technical run writes only one symbol and intraday later reads an incomplete technical signal file.

## Context

Today `intraday` was blocked with `missing_technical_levels` even though premarket had completed successfully. The root cause was that an ad hoc `EOSE` technical analysis produced a `technical_signals.json` containing only `EOSE`, which replaced the full-day technical file needed by intraday for symbols such as `MRVL`, `MU`, `AXON`, `EQIX`, and `ANET`.
