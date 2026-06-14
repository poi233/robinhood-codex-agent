# Policy Engine Intraday Migration Design

## Goal

Move the trading decision authority out of Codex prompts and into a deterministic Python policy engine, then make the intraday pipeline call that policy first. Codex, DSA, Kronos, technical analysis, and the multi-market stock report skill remain advisory research inputs. Python owns buy, sell, hold, block, and risk decisions.

This design covers the full target architecture, but the first implementation slice is the intraday policy migration. The first slice must not enable live order placement.

## Current State

The package already has:

- `trading_agent` package entrypoints for `premarket`, `intraday`, and `postmarket`.
- Premarket orchestration for market context, DSA, Kronos, technical research, planner, and archive.
- Prompt-based intraday decision logic in `src/prompts/intraday/check.txt`.
- Safety defaults in `src/config/runtime.env`, `src/config/risk.md`, `src/config/risk_tiers.json`, and `KILL_SWITCH`.
- Advisory files such as `runtime/state/runs/<date>/signals/dsa_signals.json`, `runtime/state/runs/<date>/signals/kronos_signals.json`, and `runtime/state/runs/<date>/signals/technical_signals.json`.

The current gap is that final intraday trading logic is still prompt-owned. That makes the strategy difficult to reproduce, unit test, and audit.

## Target Architecture

```text
data layer
  -> market feed / OHLCV / quotes / account snapshot / news / filings

research and signal layer
  -> DSA signals
  -> Kronos signals
  -> technical signals
  -> multi-market-stock-analysis-report-skill research summaries

policy layer
  -> deterministic Python policy
  -> buy intent / sell intent / hold / block
  -> hard risk gates

runtime layer
  -> paper
  -> review
  -> live

execution layer
  -> Robinhood review/place only after policy passes and execution is explicitly wired

review layer
  -> postmarket summary
  -> weekly and monthly strategy review
```

The policy layer is the only component allowed to decide whether an actionable order intent exists. Research tools may change score, risk flags, and explanations, but they cannot authorize trades.

## First Implementation Slice

Implement the policy engine and make `run_intraday_pipeline()` use it for the intraday decision record. Keep execution deliberately unwired in the first slice:

- `paper` mode logs `no_action` or `would_trade`.
- `review` and `live` modes may generate an order intent, but must log `blocked` with reason `execution_not_wired`.
- No first-slice code may call `review_equity_order`, `place_equity_order`, `cancel_equity_order`, or any Robinhood state-changing tool.

This lets the repo migrate decision authority without creating order-placement risk.

## Policy Package

Create:

```text
trading_agent/policy/
  __init__.py
  models.py
  loaders.py
  risk.py
  scoring.py
  buy.py
  sell.py
  engine.py
```

### `models.py`

Owns typed dataclasses:

- `Quote`: symbol, price, previous close, timestamp, and freshness status.
- `Position`: symbol, quantity, average cost, market price, and unrealized return.
- `OpenOrder`: symbol, side, quantity, notional, status.
- `PolicyInputs`: local files and runtime state needed by policy.
- `OrderIntent`: side, symbol, limit price, notional, quantity, reason codes, and confidence.
- `PolicyDecision`: decision type, optional intent, checked symbols, risk checks, reason, and blocked reasons.

`OrderIntent.side` must support both `buy` and `sell`. `sell` always means reducing an existing long position. It never means opening a short position.

### `loaders.py`

Reads local state into `PolicyInputs`:

- `src/config/universe.txt`
- `src/config/risk_tiers.json`
- `src/config/runtime.env`-derived mode and tier values
- `runtime/state/daily_plan.json`
- `runtime/state/dynamic_allowlist.json`
- `runtime/state/today_allowlist.txt`
- `runtime/state/daily_usage.json`
- `runtime/state/runs/<date>/signals/dsa_signals.json` when present
- `runtime/state/runs/<date>/signals/kronos_signals.json` when present
- `runtime/state/runs/<date>/signals/technical_signals.json` when present
- `runtime/state/research_runtime/reports/YYYY-MM-DD/*.json` when present

The first slice may use empty quotes, positions, and open orders when no broker/account adapter exists. Missing market/account data should fail closed unless a test fixture supplies it.

### `risk.py`

Owns hard no-trade gates:

- `KILL_SWITCH` exists.
- Today is missing from `daily_plan.json` or `today_allowlist.txt`.
- `market_regime` is `risk_off` or `no_trade` for buy intent.
- Symbol is outside `src/config/universe.txt`.
- Symbol is outside `runtime/state/today_allowlist.txt`.
- Symbol is outside `daily_plan.today_watchlist`.
- Missing or stale quote data.
- Existing open order for same symbol.
- Single-order or daily notional cap exhausted.
- Existing losing position blocks automatic average-down buys.
- `review` or `live` execution is not wired in the first slice.

Risk checks return structured booleans and reason codes. They do not print, call Codex, or call broker APIs.

### `scoring.py`

Owns policy score calculation. First slice score sources:

- `dynamic_allowlist.symbol_scores[symbol].score`
- DSA action or risk flags
- Kronos direction and confidence
- technical action, entry zone, no-trade zone, and invalidation levels
- multi-market research advisory fields when present

Research skill output can promote or demote a candidate, but hard risk gates override it.

### `buy.py`

Evaluates buy intent:

- `daily_plan.allowed_actions` includes `small_limit_buy`.
- Symbol passes universe, daily allowlist, and daily watchlist intersection.
- Score is at least 80, or at least 75 only for broad ETF defensive deployment when the daily plan explicitly allows it.
- Technical no-trade zone is not active.
- Price is inside the entry zone or satisfies the daily plan entry condition.
- Price is not above a do-not-chase threshold when present.
- No open order exists for the symbol.
- Daily and single-order caps have room.
- Existing losing long position is not averaged down automatically.

Buy intents are long equity or ETF limit orders only.

### `sell.py`

Evaluates sell intent:

- Only existing long positions are eligible.
- The sell quantity cannot exceed current long quantity.
- The policy must never generate a short.
- `daily_plan.allowed_actions` includes `partial_take_profit`, `risk_exit`, or a first-slice equivalent sell permission.
- Partial take-profit is allowed when unrealized return is above the configured threshold, default 2.5%.
- Risk exit is allowed when price violates an invalidation level or the daily plan explicitly directs risk reduction.
- `technical_signals.short_setup` can only reduce or exit an existing long. It cannot authorize a short entry.

Sell intents are limit sell orders only. If sell data is missing or inconsistent, the policy blocks rather than guessing.

### `engine.py`

Owns `generate_order_intent(inputs: PolicyInputs) -> PolicyDecision`.

Decision priority:

1. Global hard blocks.
2. Sell/risk-reduction candidates for existing long positions.
3. Buy candidates.
4. Hold/no-action.

The function is pure. It does not read files, write files, call Codex, call Robinhood, or inspect the live environment.

## Intraday Migration

Modify `trading_agent/orchestration/intraday.py`:

```text
run_intraday_pipeline()
  -> existing calendar/time/KILL_SWITCH gates
  -> load policy inputs from local files
  -> generate_order_intent()
  -> append exactly one decision JSONL record
  -> do not call Codex as the final trading decision source
```

The first implementation may keep `run_codex_prompt()` available for future explanation/review flows, but it must not be the authority for trade decisions.

Decision log output should remain compatible with the existing prompt contract where practical:

```json
{
  "timestamp": "ISO-8601 timestamp with timezone",
  "run_kind": "intraday",
  "trading_mode": "paper|review|live",
  "checked_symbols": ["SPY", "QQQ"],
  "decision": "kill_switch_skip|no_action|would_trade|reviewed_no_place|review_blocked|placed_order|blocked",
  "action_taken": "none",
  "proposed_order": null,
  "reason": "short reason",
  "risk_checks": {},
  "order_id_if_any": null
}
```

First-slice `review` and `live` modes must log `blocked` with `action_taken="none"` and `reason` containing `execution_not_wired`.

## Multi-Market Stock Report Skill Integration

The repository may use `Kenneth2378/multi-market-stock-analysis-report-skill` as a research report generator for A-shares, B-shares, Hong Kong stocks, and US stocks. It belongs in the advisory research layer.

Target artifact paths:

```text
runtime/reports/research/YYYY-MM-DD/<SYMBOL>.pdf
runtime/state/research_runtime/reports/YYYY-MM-DD/<SYMBOL>.json
```

The structured JSON summary should contain only policy-safe fields:

```json
{
  "date": "YYYY-MM-DD",
  "symbol": "NVDA",
  "data_status": "ok|partial|failed|stale",
  "research_bias": "bullish|neutral|bearish|avoid",
  "valuation_risk": "low|medium|high|unknown",
  "technical_structure": "uptrend|range|downtrend|breakout|pullback|unknown",
  "catalyst_quality": "strong|moderate|weak|none|unknown",
  "invalidation_condition": "short text",
  "risk_flags": ["earnings_risk"],
  "confidence": 0.0,
  "source_report": "runtime/reports/research/YYYY-MM-DD/NVDA.pdf"
}
```

The skill cannot:

- Directly authorize buy or sell.
- Expand the trading universe.
- Bypass `KILL_SWITCH`, `risk.md`, risk tiers, quote checks, daily plan, or allowlists.
- Open short positions.
- Convert a missing quote or stale daily plan into a tradeable setup.

## Testing Strategy

Add tests:

```text
tests/test_policy_buy.py
tests/test_policy_sell.py
tests/test_policy_risk.py
tests/test_policy_engine.py
tests/test_intraday_policy_integration.py
tests/test_research_skill_integration.py
```

First-slice required cases:

- `KILL_SWITCH` present blocks trading.
- Missing daily plan blocks trading.
- Stale daily plan blocks trading.
- Symbol outside universe blocks trading.
- Symbol outside today allowlist blocks trading.
- Score below threshold blocks buy.
- Missing quote blocks trading.
- Existing open order blocks new order.
- Daily cap exhausted blocks buy.
- Single-order cap exceeded is clipped or blocked according to risk rule.
- Existing losing long position blocks average-down buy.
- Sell intent cannot exceed existing long quantity.
- `short_setup` cannot open a short.
- Research skill bullish output cannot override a hard risk failure.
- Paper mode logs `would_trade` without review/place.
- Review/live first-slice logs `blocked` with `execution_not_wired`.

## Safety Requirements

- Do not enable live trading in the first implementation slice.
- Do not call Robinhood review/place/cancel from the policy engine.
- Do not call Robinhood review/place/cancel from first-slice intraday migration.
- Do not remove or weaken `KILL_SWITCH`.
- Do not raise `RISK_TIER`.
- Do not increase notional caps.
- Do not trade options, crypto, futures, margin, shorts, leveraged ETFs, or inverse ETFs.
- If data is missing, stale, conflicting, or hard to reconcile, log no action or blocked.

## Success Criteria

The first implementation slice is successful when:

- `trading_agent.policy` exists and is importable.
- `generate_order_intent()` is pure and unit-tested.
- Buy, sell, hold, and block decisions are represented.
- Intraday no longer depends on Codex prompt output for final trade decisions.
- First-slice review/live execution remains blocked.
- Existing tests pass.
- New policy and intraday integration tests pass.

## Deferred Work

- Broker/account snapshot adapter.
- Robinhood review/place execution adapter.
- Research skill installation automation.
- Postmarket policy attribution report.
- Weekly and monthly experiment tracking.
