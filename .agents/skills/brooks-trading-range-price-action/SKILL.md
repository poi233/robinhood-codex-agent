---
name: brooks-trading-range-price-action
description: Use when reading bar-by-bar price action in liquid markets and the key decision is whether a range breakout should be traded as success, failure, pullback continuation, or fade with explicit stop and target logic.
---

# Brooks Trading Range Price Action

## Overview
Use this skill to trade ranges and range-to-trend transitions with bar-by-bar logic. The default stance is skepticism: most breakouts fail, and uncertainty should be treated as trading-range behavior until proven otherwise.

## Required Inputs
- Instrument and session.
- Execution-timeframe OHLC bars.
- The left side of the chart far enough back to see the larger range or trend.
- Planned stop size and unit size before entry.

## Core Beliefs
- When uncertain, assume the market is in a trading range.
- Most breakout attempts fail.
- Countertrend trades need better prices or stronger confirmation than with-trend trades.
- A trade should have at least two independent reasons.

## Workflow
1. Read context from left to right.
Mark:
- larger trading range or trend
- magnets: prior high or low, measured move, moving average, trend line, gap, session extreme
- whether the current breakout is actually still inside a larger range

2. Judge the breakout.
Treat a breakout as stronger when it has:
- large trend body
- small tails
- follow-through in the next two or three bars
- clear violation of nearby support or resistance
- urgency, meaning shallow pullbacks during the breakout

If those are missing, assume failure is likely.

3. Pick the setup family.
- breakout continuation
- breakout pullback
- failed breakout fade
- high 1 or high 2 in a bull context
- low 1 or low 2 in a bear context
- wedge high 3 / low 3
- double top or double bottom at a range edge
- tight trading range breakout mode

4. Choose the entry style.
- In a strong trend, favor stop entries with the trend or the first pullback.
- Near the edge of a larger range, prefer pullbacks, fades, or second entries over chasing closes.
- For countertrend reversals, prefer the second signal unless the first signal is unusually strong.

5. Define stop, target, and equation.
- Stop goes beyond the signal bar, swing point, or opposite side of the range, depending on context.
- First target is the nearest magnet.
- Second target is a measured move or the opposite side of the range.
- If reward is not meaningfully larger than risk, pass.

6. Manage after entry.
- If the breakout gets immediate follow-through, hold for a swing, not a scalp.
- If follow-through stalls and bars overlap, downgrade the trade back to range logic.
- If the market becomes two-sided, reduce size or exit rather than arguing with the chart.

## Reference Router
Use these files when the chart needs more precision:

- `references/range-vs-trend.md`: state classification
- `references/breakout-quality.md`: breakout strength checklist
- `references/breakout-failure-and-fade.md`: failure logic and reversal behavior
- `references/h1-h2-l1-l2.md`: bar-counting entries
- `references/wedge-double-top-bottom.md`: exhaustion and reversal structures
- `references/magnets-and-measured-moves.md`: targets and pull magnets
- `references/trade-management.md`: stops, targets, scaling, downgrade rules
- `references/common-misreads.md`: recurring interpretation errors

## Casebook Router
- `casebook/breakout-pullback-cases.md`: continuation after strong breakouts
- `casebook/failed-breakout-fade-cases.md`: failed-breakout reversals
- `casebook/h1-h2-l1-l2-cases.md`: second-entry structures
- `casebook/range-to-trend-transition-cases.md`: regime transition studies
- `casebook/session-regime-shift-cases.md`: intraday regime shifts and downgrade logic
- `casebook/ticker-case-map.md`: which core tickers best teach which Brooks patterns

After any substantial live-market research that reveals a reusable pattern, route the result into `trading-research-casebook-maintenance`.

## Quick Heuristics
- Do not buy strong bull closes near the top of a larger range unless the larger range has clearly ended.
- The first pullback after a strong breakout is often the better entry than the breakout bar itself.
- High 2 and Low 2 are workhorse setups because they package context, failed first attempt, and clearer risk.
- High 3 or Low 3 often behaves like a wedge. Respect the possibility of exhaustion.

## Common Mistakes
- Treating every strong bar as trend when it is only a spike inside a larger range.
- Taking a breakout with no second reason.
- Using the same stop logic in a trend and in a range.
- Refusing to downgrade back to range behavior once overlap returns.

## Output Template
```text
Context:
Setup family:
Why the breakout should succeed or fail:
Entry:
Stop:
Target 1:
Target 2:
What would downgrade this back to range logic:
Pass condition:
```
