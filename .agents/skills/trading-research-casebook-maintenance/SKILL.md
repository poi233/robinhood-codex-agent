---
name: trading-research-casebook-maintenance
description: Use when a completed market or company analysis contains a reusable pattern, edge case, or failure lesson that should be added back into the trading and investing skill casebooks for future retrieval.
---

# Trading Research Casebook Maintenance

## Overview
Use this skill after a substantive technical or fundamental research task to convert the result into durable casebook knowledge. The goal is not to save every analysis. The goal is to capture reusable patterns, traps, and edge cases that improve future judgment.

## When To Add A Case

Add or update a case when the research revealed at least one of these:

- a clean textbook pattern worth reusing
- a false positive that future analysis should avoid
- an edge case that sits between two pattern families
- a multi-timeframe conflict worth preserving
- a fundamental quality or valuation lesson that generalizes beyond one ticker

Do not add a case if the work contains no reusable lesson.

## Workflow
1. Classify the research output as:
- `chan`
- `brooks`
- `fundamentals`
- or multi-skill if the lesson crosses boundaries

2. Identify the pattern family using `references/pattern-tag-taxonomy.md`.

3. Choose whether to:
- append to an existing pattern file
- create a new subsection in the right file
- or add a cross-reference in more than one skill

4. Write the case using `templates/case-intake-template.md`.

5. Add one log entry to `case-update-log.md`.

## Required Fields
- ticker or instrument
- date range or reporting period
- timeframe if technical
- context
- observed setup or thesis
- why it looked attractive
- why it worked or failed
- correct interpretation
- operational takeaway
- pattern tags

## Reference Router
- `references/research-to-casebook-rules.md`: capture rules
- `references/pattern-tag-taxonomy.md`: normalized tags
- `references/focus-universe.md`: current default study universe

## Output Rule

Every casebook update should leave behind:

- one improved casebook entry
- one log line in `case-update-log.md`
- tags that make the lesson searchable later
