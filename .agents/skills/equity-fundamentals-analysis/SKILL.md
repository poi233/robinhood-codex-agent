---
name: equity-fundamentals-analysis
description: Use when evaluating a listed company from a fundamental investor perspective and the task requires judging business quality, statement quality, valuation, capital allocation, or financial red flags rather than short-term price action.
---

# Equity Fundamentals Analysis

## Overview
Use this skill to turn a public company into a decision-oriented fundamental memo. The goal is to identify what the business does, how it makes money, whether the economics are high quality, what can break, and what valuation framework fits.

## Required Inputs
- Company name or ticker.
- Latest reported financials if available.
- At least one business description source.
- Price or valuation context if the task includes attractiveness, not just business quality.

## Hard Rules
- Do not start with valuation before understanding the business model.
- Separate reported facts, management claims, derived conclusions, and assumptions.
- Revenue growth alone is never enough evidence of quality.
- Earnings quality and cash conversion must be checked before trusting optically cheap valuation.
- If key data is missing, output `needs more data` instead of pretending certainty.

## Workflow
1. Identify the business.
What is sold, to whom, through what model, and what drives repeat demand?

2. Identify the economic engine.
What drives revenue, gross margin, operating leverage, reinvestment needs, and cash conversion?

3. Read the statements.
Use income statement, balance sheet, and cash flow statement together. Look for consistency, not isolated ratios.

4. Judge quality.
Classify:
- high-quality compounder
- cyclical but understandable
- capital-intensive with financing dependence
- low-visibility or low-quality growth

5. Judge capital allocation.
Check buybacks, dilution, M&A, debt usage, dividends, and reinvestment discipline.

6. Choose a valuation frame.
Use the business type to decide whether the main lens should be earnings, free cash flow, EV-based multiples, asset value, or a scenario range.

7. Write the memo.
Output:
- `business_model`
- `core_drivers`
- `quality_judgment`
- `statement_read`
- `valuation_frame`
- `main_risks`
- `what_would_change_my_mind`

## Reference Router
- `references/business-quality.md`: moat, demand shape, pricing power, and business durability
- `references/financial-statement-framework.md`: how to read the three statements together
- `references/unit-economics-and-growth-quality.md`: growth quality and reinvestment logic
- `references/capital-allocation.md`: management quality through capital decisions
- `references/valuation-frameworks.md`: valuation by business type
- `references/earnings-quality-and-red-flags.md`: accounting and quality traps
- `references/balance-sheet-risk.md`: leverage and fragility
- `references/analysis-workflow.md`: full end-to-end analysis order

## Casebook Router
- `casebook/high-quality-compounder-cases.md`: durable quality businesses
- `casebook/cyclical-and-semi-cases.md`: cyclical or semi-like economics
- `casebook/valuation-trap-cases.md`: price and narrative traps
- `casebook/capital-allocation-cases.md`: management behavior through capital use
- `casebook/earnings-quality-red-flag-cases.md`: accounting and statement risk patterns
- `casebook/ticker-case-map.md`: where each core ticker teaches the most

After any substantial company research that produces a reusable lesson, route the result into `trading-research-casebook-maintenance`.

## Quick Heuristics
- Good businesses can still be bad stocks if the entry valuation assumes perfection.
- Cheap stocks are often cheap because the balance sheet or earnings quality is worse than the headline multiple suggests.
- Capital allocation is often the hidden difference between a decent business and a great investment.
- If the company needs constant external financing to sustain its story, do not treat revenue growth as proof of strength.

## Output Template
```text
Business model:
Core drivers:
Quality judgment:
Statement read:
Capital allocation read:
Valuation frame:
Main risks:
What would change my mind:
```
