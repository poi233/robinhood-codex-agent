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
