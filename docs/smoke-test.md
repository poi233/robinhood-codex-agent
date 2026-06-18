# Smoke test (integration checklist)

One command to answer "is the whole system still wired up end-to-end?" after a change. It runs the
read-only / local command surface and prints a PASS/FAIL summary. Best-effort: every step runs even
if an earlier one fails; it exits non-zero only if a **required** step fails.

```bash
./src/scripts/smoke/run_smoke.sh
```

## What it runs

| Group | Steps | Needs |
|---|---|---|
| Config + safety | `doctor` · `safety/check_safety.sh` · `launchd/check_launchd_plists.sh` | local |
| Read-only analytics | `analytics build` · `fill-quality` · `weight-suggestion` · `snapshot` · `trend` · `nightly-health` · `replay` | local |
| Self-growth (paper/shadow only) | `growth observe` · `propose` · `shadow` · `evaluate` | local |
| Network analytics (opt-in) | `analytics calibrate` · `ai-signal-study` · `ai-ablation` | yfinance |
| Lifecycle dry-runs (opt-in) | `premarket` (dry-run) · `intraday` (outside-market) · `postmarket` · `nightly-analysis` (dry-run) | Codex/MCP |

Opt into the heavier groups:

```bash
SMOKE_INCLUDE_NETWORK=1 ./src/scripts/smoke/run_smoke.sh                       # also the yfinance analytics
SMOKE_INCLUDE_NETWORK=1 SMOKE_INCLUDE_LIFECYCLE=1 ./src/scripts/smoke/run_smoke.sh   # also dry-run the lifecycle
```

Network and lifecycle steps are marked `FAIL(opt)` if they fail and do **not** fail the smoke (they
depend on a network/Codex/market-time that won't always be present). Required steps are the local,
deterministic ones — those must stay green.

## When to run it

- After any change before pushing (alongside `python3 -m pytest tests/ -q`).
- As the first thing in a fresh checkout, to confirm config + entry points resolve.
- After a dependency or Python-version bump.

## Unit tests vs smoke

`pytest` proves the pure logic; the smoke proves the **wiring** (CLI dispatch, config resolution,
file paths, report generation) actually runs as a whole. Run both:

```bash
python3 -m pytest tests/ -q          # logic
./src/scripts/smoke/run_smoke.sh     # wiring
```

See also [`daily-strategy-playbook.md`](./daily-strategy-playbook.md) for the day-to-day operational
loop, and [`project-status.md`](./project-status.md) for current capability status.
