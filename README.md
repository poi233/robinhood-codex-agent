# Robinhood Codex Agent

Low-frequency trading automation for a single dedicated Robinhood Agentic Account. The day splits
into three phases:

- **Premarket** — Codex (LLM) + the Robinhood Trading MCP gather data and write a **daily plan**.
- **Intraday** — **deterministic Python** reads the premarket snapshots, refreshes live quotes, runs
  a policy engine, and (in paper mode) updates a local simulated ledger. **Never calls Robinhood.**
- **Postmarket** — day-end paper ledger + performance summary + a Codex review.

The system is conservative and **fail-closed**: missing or stale data → do nothing.

> Automation infrastructure, **not financial advice**. Live trading can lose money. Real order
> placement is intentionally **not wired** in Python (fails closed with `execution_not_wired`). Keep
> it in paper mode until the logs are boring and correct.

---

## Quick Start

```bash
# 0. One-time setup (Codex + Robinhood MCP + Kronos) — see "Setup" below.

python3 -m trading_agent doctor        # print effective config — run this first when unsure

# Run a paper day:
python3 -m trading_agent premarket     # gather data → daily plan (the only phase that calls MCP)
python3 -m trading_agent intraday      # one policy decision per run (repeat every ~30 min)
python3 -m trading_agent postmarket    # day-end paper summary + Codex review

# Look at results:
python3 -m trading_agent replay            # fill rate + blocked-reason stats
python3 -m trading_agent analytics build   # build runtime/analytics/analytics.db
python3 -m trading_agent dashboard         # read-only Streamlit UI (localhost:8501)
```

Defaults are paper-only and safe. The canonical operational path is the shell wrappers in
`src/scripts/entrypoints/` (they export the cron/launchd defaults); the `python3 -m trading_agent`
commands are equivalent for manual use and accept `--dry-run`.

---

## System overview

```mermaid
flowchart LR
    Sched["cron / launchd / manual"] --> PM["① premarket<br/>(Codex + Robinhood MCP)"]
    PM -->|writes| Snap["dated run folder<br/>runtime/state and logs<br/>/runs/YYYY-MM-DD/"]
    Snap --> ID["② intraday<br/>(deterministic Python)"]
    ID -->|live quotes| YF["yfinance"]
    ID -->|paper fills| Ledger["local paper ledger"]
    Snap --> PO["③ postmarket<br/>(summary + Codex review)"]
    Ledger --> PO
    ID -->|decisions.jsonl| An["replay / analytics / dashboard"]
    Ledger --> An
    An -.nightly, read-only.-> Growth["self-growth + calibration<br/>(proposes, never auto-applies)"]
```

Premarket owns **reasoning** (Codex: DSA classification, technical research, catalysts, narrative).
Deterministic Python owns the **numbers** (capital, scoring, risk overlay, sizing, fills) — so the
parts that move money are testable and reproducible, and the LLM is advisory only.

---

## ① Premarket pipeline — building the daily plan

`premarket` runs a fixed DAG. Sequential prerequisites first, then two **parallel** fan-out stages,
then a deterministic score→plan tail. Every step writes a JSON artifact into the dated run folder;
each box below is annotated with what it produces. **Advisory** steps (wrapped so a failure never
breaks the run) are the LLM/model signal layers.

```mermaid
flowchart TD
    subgraph S1["1 · Account and market context (sequential)"]
        direction TB
        A1["account_snapshot<br/><i>positions, buying power</i>"] --> A2["capital_snapshot<br/><i>deployable capital</i>"] --> A3["market_context<br/><i>OHLCV via yfinance/MCP</i>"]
    end

    subgraph S2["2 · Signal layers (parallel · advisory)"]
        direction LR
        B1["DSA scan (Codex)<br/><i>theme/priority/crowding<br/>full universe ~88</i>"]
        B2["Kronos forecast<br/><i>price bias · watchlist ≤30</i>"]
        B3["technical research (Codex)<br/><i>entry/stop/target levels</i>"]
        B4["market_calendar (Codex)"]
        B5["quote_snapshot_core (Codex)"]
        B6["price factors (H2)<br/><i>factor_panel + factor_alpha</i>"]
    end

    subgraph S3["3 · Candidate set (sequential)"]
        direction TB
        C1["trader_watch_levels"] --> C2["candidate_merge<br/><i>candidate_snapshot.json</i>"] --> C3["quote_snapshot_candidates"]
    end

    subgraph S4["4 · Candidate enrichment (parallel · advisory)"]
        direction LR
        D1["tradability_candidates"]
        D2["catalyst_enrichment (Codex)<br/><i>events, earnings risk</i>"]
    end

    subgraph S5["5 · Score and plan (deterministic)"]
        direction TB
        E1["ai_signals (H3)<br/><i>normalize DSA/Kronos/catalyst<br/>→ ai_signals.json</i>"] --> E2["data_status_summary<br/><i>fail-closed gate</i>"]
        E2 --> E3["candidate_scoring<br/><b>5-component weighted score</b><br/><i>→ candidate_scores.json</i>"]
        E3 --> E4["risk_overlay<br/><i>regime · watchlist · tradable<br/>· allowed_actions</i>"]
        E4 --> E5["final_planner (Codex)<br/><b>daily_plan.json</b>"] --> E6["archive"]
    end

    S1 --> S2 --> S3 --> S4 --> S5
```

**Candidate scoring (step 5, E3)** — the deterministic 5-component weighted score that ranks the
universe. Each component is scaled by its own confidence before weighting:

| Component | Weight | Source |
|---|---|---|
| `technical` | 0.30 | technical research levels / action |
| `dsa` | 0.25 | DSA theme + promote/demote classification |
| `catalyst` | 0.20 | catalyst enrichment |
| `kronos` | 0.15 | Kronos price-forecast bias |
| `quote` | 0.10 | live quote freshness/quality |

→ `candidate_score`. **risk_overlay** then sorts candidates, applies regime/concentration caps, and
emits `watchlist_candidates`, `tradable_candidates`, and `allowed_actions`, which **final_planner**
turns into `daily_plan.json` — the single contract intraday consumes.

> **Active watchlist vs universe**: the cheap DSA scan runs over the full `universe.txt` (~88
> symbols); the expensive layers (Kronos, market_feed, technical) run only over
> `active_watchlist.txt` (≤30), falling back to the full universe if absent.

---

## ② Strategy — how one intraday decision is made

`intraday` is pure deterministic Python. It loads the premarket artifacts, **refreshes live quotes**
(snapshot quotes are never a valid execution fallback), then runs the policy engine, which is a
chain of **fail-closed gates** followed by **sell-first, then buy**. It appends exactly one decision
per run and, in paper mode, updates the local ledger.

Both `intraday` and `postmarket` now resolve the repo root from the code location or an explicit
`AGENT_ROOT` override, so they do not depend on the launchd working directory. `postmarket` also
resolves the `codex` executable from `CODEX_BIN`, `PATH`, or common install locations, which avoids
the launchd-only `codex: not found` failure.

```mermaid
flowchart TD
    Start["intraday run"] --> Load["load daily_plan + account + scores<br/>+ refresh live quotes (yfinance)"]
    Load --> Gates{"fail-closed gates<br/>kill_switch · missing/stale plan ·<br/>missing account · data blocked ·<br/>risk_overlay blocks trading"}
    Gates -->|any trips| Blocked["blocked / no_action<br/><i>(do nothing)</i>"]

    Gates -->|all pass| Sell["evaluate_sell — runs FIRST"]
    Sell --> HS{"any position loss vs cost<br/>over HARD_STOP_LOSS_PCT<br/>(default 8%)?"}
    HS -->|yes| SellOrder["SELL · catastrophic_stop<br/><i>full exit, no levels needed</i>"]
    HS -->|no| Exit{"take-profit target hit?<br/>or price ≤ invalidation level?"}
    Exit -->|yes| SellOrder
    Exit -->|no| Buy["evaluate_buy"]

    Buy --> Allowed{"plan allows small_limit_buy<br/>and regime not risk_off?"}
    Allowed -->|no| NoAction["no_action"]
    Allowed -->|yes| Rank["rank candidates by<br/><b>trade_readiness_score</b>"]
    Rank --> PriceGate{"per candidate:<br/>in entry zone? · no chase? ·<br/>reward:risk OK? · size ≥ min?"}
    PriceGate -->|first that clears| BuyOrder["BUY · limit order"]
    PriceGate -->|none clears| NoAction

    SellOrder --> Mode{"trading_mode"}
    BuyOrder --> Mode
    Mode -->|paper| Fill["paper broker fill<br/><i>conservative model + slippage<br/>→ local ledger</i>"]
    Mode -->|review / live| Unwired["blocked · execution_not_wired<br/><i>(human-gated, never auto)</i>"]
```

**Buy ranking (`trade_readiness_score`)** — a 6-component blend used to order survivors of the hard
blocks; the highest-ranked candidate that also clears the price/size gates becomes the order:

```
trade_readiness_score = 0.35·candidate_score + 0.25·technical + 0.15·price_setup
                      + 0.10·liquidity + 0.10·research + 0.05·catalyst
```

Key properties: **sell is evaluated before buy** (risk reduction wins ties); the **catastrophic hard
stop** guarantees every position has an automatic exit even with no technical levels and a plan that
permits no discretionary sell; **review/live placement is never wired** in Python — it always blocks
with `execution_not_wired`, so only a human can take it live.

---

## Using each command

### Daily lifecycle
| Command | What it does |
|---|---|
| `premarket` | Full premarket pipeline → `daily_plan`, candidate scores, risk overlay. The only phase that talks to Robinhood MCP. |
| `intraday` | Deterministic sell-then-buy policy + paper broker; refreshes live quotes; appends exactly one decision per run. No MCP calls. |
| `postmarket` | Paper day-end ledger + performance summary + Codex review. |
| `dsa` | Standalone DSA signal scan (also runs inside premarket). |

### Inspect & analyze (all read-only)
| Command | What it does |
|---|---|
| `doctor` | Print effective config (mode, tiers/caps, feature flags) and exit. |
| `replay [--since --until --output]` | Local paper analytics: fill rate + blocked-reason distribution across run dates. |
| `analytics build [--since --until]` | (Re)build `runtime/analytics/analytics.db` (SQLite) from run state — feeds the dashboard. |
| `analytics calibrate [--since --until]` | E1 calibration → `calibration_report.{json,md}`: score-bucket forward returns (1/5/21/63d) + excess vs SPY, multi-horizon Rank IC + t-stat, benchmark alpha, setup outcomes. |
| `analytics fill-quality [--since --until]` | E4 → `fill_quality_report.{json,md}`: realized per-order slippage + conservative-fill sensitivity (how much paper edge shrinks under spread-aware fills). |
| `analytics ai-signal-study [--since --until]` | H3 → `ai_signal_study.{json,md}`: per-AI-layer confidence calibration, directional accuracy, confidence→return IC, reason/warning-code lift. |
| `analytics ai-ablation [--since --until]` | H3 → `ai_ablation.{json,md}`: per-AI-layer marginal IC (leave-one-out) + factor-only and AI+factor comparison. |
| `analytics weight-suggestion [--horizon --damping]` | E2 → `weight_suggestion.json`: IC-backed scoring-weight **suggestion**. Never auto-applied (adopt via a new strategy version + shadow run). |
| `analytics snapshot [--date]` | I2: archive a dated copy of tonight's reports to `runtime/analytics/history/<date>/` + `nightly_summary.json`. Idempotent. |
| `analytics trend [--since --until --output]` | I3: aggregate `history/*/nightly_summary.json` into per-metric time series → `trend.json`. |
| `analytics nightly-health` | L4 → `nightly_health.json`: report freshness + the last nightly run's failed steps. Surfaced as a 🟢/🔴 banner on the dashboard Trends tab. |
| `dashboard` | Read-only Streamlit UI (`localhost:8501`): 9 tabs — Today / Candidates / Decisions / Paper / Strategy Comparison / Calibration / Self-Growth / Themes / Trends. |

### Nightly batch (read-only / shadow-only)
`src/scripts/entrypoints/run_nightly_analysis.sh` runs the analytics + self-growth commands best-effort
after the close (rebuild DB → calibrate → fill-quality → AI study/ablation → weight-suggestion →
growth observe/propose/validate/shadow/evaluate → snapshot → trend). It never trades, approves, or
promotes. Gated by `ENABLE_NIGHTLY_ANALYSIS` (default 1).

### Self-growth (paper/shadow only — proposes, never auto-applies)
Diagnoses the system, proposes **bounded** experiments, runs challenger strategies in **shadow
paper**, and recommends promotions — but it **never** edits the champion strategy or auto-promotes to
live. Promotion is always a manual `strategy_registry.yaml` edit by a human.

```bash
python3 -m trading_agent growth observe        # diagnose → growth_observations.json
python3 -m trading_agent growth propose        # write bounded, whitelist-only proposals (enables nothing)
python3 -m trading_agent growth validate runtime/strategy_proposals/<date>/
python3 -m trading_agent growth experiments add  runtime/strategy_proposals/<date>/proposal_001_*.json
python3 -m trading_agent growth experiments approve <experiment_id>   # human gate: enables shadow only
python3 -m trading_agent growth shadow         # run challengers in isolated shadow ledgers
python3 -m trading_agent growth recommend      # compare champion vs challengers
python3 -m trading_agent growth promote check <experiment_id>         # drafts a changelog only
```

Permanently forbidden from any mutation (hard-coded): `TRADING_MODE`, `RISK_TIER`, `PAPER_RISK_TIER`,
`KILL_SWITCH`, MCP approval, `place_equity_order`, `per_trade_risk_pct`, `max_daily_risk_pct`,
`max_single_stock_weight`. Full design: [`docs/roadmap.md`](docs/roadmap.md) G phase.

---

## Safe by default

| Setting | Default | Meaning |
|---|---|---|
| `TRADING_MODE` | `paper` | Simulated fills only; no real orders |
| `RISK_TIER` | `3` | Live/review caps ($5k single / $20k daily) |
| `PAPER_RISK_TIER` | `4` | Paper-only "paper_max" ($100k/$400k); caps high so risk-budget binds |
| `PAPER_STARTING_CASH` | `400000` | Paper ledger seed cash |
| `HARD_STOP_LOSS_PCT` | `0.08` | Catastrophic auto-exit threshold (paper); `0` disables |
| `KILL_SWITCH` | present | Hard stop for review/live intraday; paper may still run |

**Hard rules:** dedicated Agentic account only · long equities/ETFs only (no options/crypto/futures/
margin/shorts) · limit orders only · notional capped by tier + daily plan · missing/stale data → do
nothing · DSA/Kronos/technical/factor/fundamental signals are advisory only · real execution unwired
in Python. Verify with `./src/scripts/safety/check_safety.sh`.

**Risk tiers** (`src/config/risk_tiers.json`; effective tier depends on `TRADING_MODE`):

| Tier | Single / Daily | Use |
|---|---|---|
| 0–2 | $10/$25 → $50/$150 | live micro → moderate |
| 3 | $5k / $20k | small dedicated live |
| 4 | $100k / $400k | **paper only** |

In paper mode the binding constraints are `per_trade_risk_pct` and the portfolio-weight caps, not the
dollar ceiling. `doctor` prints the effective tier and caps.

---

## Configuration (`src/config/`)

Key files: `runtime.env` (defaults; `runtime.env.local` for machine overrides, git-ignored) ·
`risk_tiers.json` · `policy_profiles.json` · `scoring_profiles.yaml` · `universe.txt` /
`active_watchlist.txt` · `strategy_registry.yaml` (active strategy version) · `growth_policy.json`
(self-growth safety boundary) · `risk.md` / `strategy.md` (human-readable rules).

```bash
TRADING_MODE=paper
RISK_TIER=3 / PAPER_RISK_TIER=4
PAPER_STARTING_CASH=400000
PAPER_FILL_MODEL=conservative / PAPER_SLIPPAGE_BPS=10 / HARD_STOP_LOSS_PCT=0.08
ENABLE_DSA_SIGNAL_LAYER / ENABLE_KRONOS_SIGNAL_LAYER / ENABLE_TECHNICAL_SIGNAL_LAYER=1
ENABLE_NIGHTLY_ANALYSIS=1   # ENABLE_EVIDENCE_PROPOSALS / ENABLE_SHADOW_RESCORE=0 (in development)
```
Precedence: shell exports > `runtime.env.local` > `runtime.env` > `strategy_registry.yaml` defaults.
`doctor` shows the resolved values and every feature flag.

> **Generated state/logs** under `runtime/` are git-ignored (they contain account size, decisions,
> symbols, timestamps). Machine-specific values go in `src/config/runtime.env.local` (also ignored).

---

## Setup

```bash
# Codex + Robinhood MCP
codex login
codex mcp add robinhood-trading --url https://agent.robinhood.com/mcp/trading
codex; /mcp        # complete Agentic Account auth on desktop

# Repo-owned trading skills (advisory context for technical research; cannot authorize trades)
./src/scripts/skills/install_repo_skills.sh && ./src/scripts/skills/verify_repo_skills.sh

# Portable Kronos (needs git + Python 3.11/3.12; prefers python3.12)
KRONOS_BOOTSTRAP_PYTHON=$(command -v python3.12) ./src/scripts/kronos/setup_kronos_env.sh
./src/scripts/kronos/verify_kronos_env.sh
```

Optional dashboard dependency: `pip install -e ".[dashboard]"` (streamlit).

---

## Tests & dry runs

```bash
python3 -m pytest tests/ -q                                            # unit tests
CODEX_EXEC_DRY_RUN=1 ./src/scripts/entrypoints/run_premarket.sh        # dry-run without Codex
ALLOW_OUTSIDE_MARKET_TEST=1 ./src/scripts/entrypoints/run_all_paper_once.sh   # full paper lifecycle
```

---

## Schedule & rollout

Scheduled (America/Los_Angeles) via `cron.example` / `launchd/*.plist.example`: `05:30` premarket ·
`06:45`–`12:45` intraday every 30 min · `13:10` postmarket · `20:00` nightly analysis (weekdays).

Rollout: paper → review → live tier 0, advancing only after clean logs. A human removes `KILL_SWITCH`
and sets `RISK_TIER`; Codex never does. Postmarket may *recommend* a tier change; a human makes it.

---

## Docs

- [`docs/daily-strategy-playbook.md`](docs/daily-strategy-playbook.md) — **what to do each day/week/month to keep improving the strategy** (start here for operations).
- [`docs/roadmap.md`](docs/roadmap.md) — prioritized work, phase by phase, with status.
- [`docs/project-status.md`](docs/project-status.md) — block-by-block account of what's built (and what isn't).
- `docs/setup/` — setup notes · `docs/superpowers/` — design specs & plans.
