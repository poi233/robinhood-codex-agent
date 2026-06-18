# Strategy Changelog

Human-readable log of every strategy version registered in
[`src/config/strategy_registry.yaml`](../src/config/strategy_registry.yaml). Every new
or adjusted strategy version must get an entry here — version id, parent, change
reason, date, and the commit that introduced it — so `change_reason` in the registry
always has a matching record of *why* it changed, not just *what* changed.

---

## baseline_v1

- **Parent**: none (first tracked version)
- **Date**: 2026-06-15
- **Commit**: `5d95c9f` (B2: add strategy_registry.yaml + registry.py, wire into load_env_files)
- **Config**: `scoring_profile=aggressive_growth`, `policy_profile=aggressive_growth`,
  `risk_tier_live=3`, `risk_tier_paper=4`
- **Change reason**: Initial registration of the strategy in effect before this registry
  existed (`RISK_TIER=3` live / `PAPER_RISK_TIER=4` paper, `aggressive_growth` scoring +
  policy profiles, hardcoded in `runtime.env`). No behavior change — this just makes the
  existing configuration traceable as `strategy_id=baseline_v1` in `run_manifest.json`
  (B1) and `analytics.db`'s `runs` table (B3).
- **Frequency role**: low-frequency preset — ~30 min cron cadence, max 2 new positions/day,
  3-day rebuy cooldown, 1.5% max daily risk.

## midfreq_v1

- **Parent**: `baseline_v1`
- **Date**: 2026-06-18
- **Commit**: (this change — frequency presets)
- **Config**: `scoring_profile=aggressive_growth`, `policy_profile=aggressive_growth_mid`,
  `risk_tier_live=3`, `risk_tier_paper=4`
- **Change reason**: Medium-frequency preset so trade frequency is a config choice, not a
  hardcoded behavior. Pairs the ~5-minute intraday cron block with a faster policy profile:
  `max_new_positions_per_day=4`, `max_new_positions_per_week=12`, `cooldown_days_after_buy=1`,
  `max_daily_risk_pct=0.03`, `max_weekly_risk_pct=0.08`. Scoring thresholds and risk tiers are
  unchanged from `baseline_v1`; only cadence + position/risk gating differ. Now the active
  strategy. `run_intraday` remains pure Python (no Codex/LLM, no Robinhood), so the higher
  cadence adds no LLM cost — only more yfinance quote fetches.

## highfreq_v1

- **Parent**: `baseline_v1`
- **Date**: 2026-06-18
- **Commit**: (this change — frequency presets)
- **Config**: `scoring_profile=aggressive_growth`, `policy_profile=aggressive_growth_high`,
  `risk_tier_live=3`, `risk_tier_paper=4`
- **Change reason**: High-frequency preset for paper experimentation. Pairs the ~1-minute
  intraday cron block with `policy_profile=aggressive_growth_high`:
  `max_new_positions_per_day=8`, `max_new_positions_per_week=25`, `cooldown_days_after_buy=0`,
  `cooldown_days_after_stop=1`, `max_daily_risk_pct=0.06`, `max_weekly_risk_pct=0.15`, and a
  tighter `max_quote_age_seconds=300`. Registered but not active; switch `active_strategy` to
  `highfreq_v1` and enable the matching cron block to use it.
