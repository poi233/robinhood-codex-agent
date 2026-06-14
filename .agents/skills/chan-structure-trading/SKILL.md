---
name: chan-structure-trading
description: Use when analyzing liquid markets with Chan-style multi-timeframe structure and the task requires locating trend, center, divergence, and type 1, 2, or 3 buy or sell points without mixing execution levels.
---

# Chan Structure Trading

## Overview
Use this skill to turn raw price action into a structure-first trade memo. The goal is not prediction. The goal is to determine the active level, the current center or trend state, the valid buy or sell point if one exists, and the structural invalidation.

## Required Inputs
- Instrument and market type.
- At least one execution-timeframe chart with OHLC data.
- One higher timeframe for context.
- One lower timeframe only if precise entry timing is needed.

## Hard Rules
- Fix one execution level before doing any analysis. Lower levels may refine entry, but may not overrule the execution level.
- Do not call something a buy or sell point without first identifying the surrounding center or trend leg.
- If the structure is ambiguous, output `observe` instead of forcing a trade.
- A third buy or third sell is invalid once the pullback re-enters the prior center.
- Treat MACD only as a force aid. It cannot replace structural decomposition.

## Workflow
1. Choose the timeframe stack.
Higher timeframe defines context, execution timeframe defines the trade, lower timeframe only locates the entry.

2. Decompose the execution timeframe.
Mark fractals, then strokes, then segments, then centers. If the chart quality does not support this cleanly, say so.

3. Classify the current state.
Choose one:
- trend continuation
- center extension
- higher-level reversal attempt

4. Test for buy or sell points.
- Type 1: a trend-ending divergence away from the last center. This is the earliest reversal point and the least forgiving to execute.
- Type 2: the retest after type 1. Use this when the first reversal leg has already appeared and the market fails to make a fresh extreme.
- Type 3: price leaves a center, pulls back, and does not re-enter the center. This is the cleanest continuation setup.

5. Apply interval nesting only after the structure is set.
Use the lower timeframe to locate a tighter trigger inside the already chosen higher-level setup. Do not let a noisy lower-level move invent a trade that the execution level does not support.

6. Define the invalidation.
The invalidation should be structural:
- back into the prior center for a third buy or sell
- failure of the retest leg for a second buy or sell
- destruction of the divergence thesis for a first buy or sell

7. Write the trade memo.
Output:
- `context`: higher-timeframe state
- `execution_level`: chosen trading level
- `structure`: centers and main segments
- `signal`: none / type1 / type2 / type3
- `action`: buy / sell / reduce / observe
- `invalidation`: exact price or structural condition
- `next_confirmation`: what must happen next

## Reference Router
Use these files when the live chart demands more detail:

- `references/grade-selection.md`: how to choose and keep one execution level
- `references/fractals-strokes-segments.md`: decomposition grammar
- `references/centers-and-trends.md`: center formation, extension, and trend judgment
- `references/buy-sell-point-taxonomy.md`: type 1, 2, and 3 buy or sell logic
- `references/divergence-and-force.md`: divergence, force, and momentum interpretation
- `references/interval-nesting.md`: lower-level precision without losing higher-level discipline
- `references/common-misreads.md`: false signals and typical counting errors

## Casebook Router
- `casebook/type-1-reversal-cases.md`: early reversal structures
- `casebook/type-2-retest-cases.md`: retest-based reversals
- `casebook/type-3-continuation-cases.md`: continuation structures
- `casebook/false-third-buy-cases.md`: common continuation traps
- `casebook/multi-timeframe-discipline-cases.md`: top-down execution discipline
- `casebook/ticker-case-map.md`: which core tickers best teach which Chan patterns

After any substantial live-market research that reveals a reusable pattern, route the result into `trading-research-casebook-maintenance`.

## Quick Heuristics
- If you cannot point to the last center, you are not ready to call a third buy or sell.
- If the move is only a lower-timeframe bounce inside a damaged higher-timeframe structure, treat it as repair, not reversal.
- If a small-level entry opens into a larger-level trend, decide explicitly whether to keep trading the small level or upgrade the position.

## Common Mistakes
- Mixing 5-minute fear with daily structure.
- Calling every sharp rebound a second buy.
- Treating indicator divergence as enough evidence without a completed structural leg.
- Ignoring that the best-looking lower-timeframe setup may be directly into a higher-timeframe center boundary.

## Output Template
```text
Context:
Execution level:
Center(s):
Current state:
Signal:
Action:
Invalidation:
Next confirmation:
Why this is not the opposite signal:
```
