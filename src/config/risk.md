# Risk Rules

Live trading is allowed only inside the dedicated Robinhood Agentic Account.
Do not place orders in the user's ordinary Investing account, Roth IRA, Managed account, Spending account, Traditional IRA, crypto account, or any external account.

Runtime modes:
- `paper`: never call `review_equity_order` or `place_equity_order`; write `would_trade` only.
- `review`: `review_equity_order` is allowed, but `place_equity_order` is forbidden.
- `live`: `place_equity_order` is allowed only after every hard limit passes and `review_equity_order` returns no warning, ambiguity, or rejection.

Risk tiers:
- `RISK_TIER=0`: max single order `$10`, max daily notional `$25`, max 1 live order/day. This is the initial micro-test tier.
- `RISK_TIER=1`: max single order `$25`, max daily notional `$75`, max 2 live orders/day. Use only after at least 5 clean paper/review sessions.
- `RISK_TIER=2`: max single order `$50`, max daily notional `$150`, max 3 live orders/day. Use only after live tier 1 logs show no rule violations.
- `RISK_TIER=3`: max single order `$100`, max daily notional `$300`, max 4 live orders/day. Aggressive tier for a small dedicated Agentic Account only.
- The premarket plan may set a lower daily cap than the tier cap, but must never exceed the tier cap.
- Any tier increase must be made manually in `src/config/runtime.env`; Codex must not raise `RISK_TIER` by itself.

Hard limits:
- Only trade symbols that are present in all applicable gates:
  - `src/config/universe.txt`;
  - `runtime/state/today_allowlist.txt`;
  - `runtime/state/daily_plan.json.today_watchlist`.
- `src/config/allowlist.txt` is only a static emergency fallback and must not be used for normal dynamic trading.
- Only long equities or ETFs.
- Never trade options, crypto, futures, margin, short selling, leveraged ETFs, or inverse ETFs.
- Only use limit orders.
- Max single order notional is the lower of `src/config/runtime.env`, `RISK_TIER`, and `runtime/state/daily_plan.json`.
- Max daily notional is the lower of `src/config/runtime.env`, `RISK_TIER`, and `runtime/state/daily_plan.json`.
- Max one open order per symbol.
- Max one buy and one sell per symbol per day.
- Do not average down automatically if already holding a losing position.
- Do not trade if quote, account, position, order, or daily-usage data is missing, stale, or inconsistent.
- Do not trade if the dedicated Agentic Account cannot be identified unambiguously.
- Always call `get_equity_tradability` before a trade candidate.
- Always call `review_equity_order` before `place_equity_order` in `live` mode.
- If review shows any warning, ambiguity, rejection, or unexpected field, do not place the order.
- If `market_regime` is `risk_off` or `no_trade`, do not place any order.
- If `KILL_SWITCH` exists, do not place any order.
- If `runtime/state/today_allowlist.txt` is missing, stale, empty, or not generated today, do not place any order.
- If local time is outside the configured intraday window, do not place any order.
- If there is already an open order for a symbol, do not place another order for that symbol.
- Never cancel orders automatically in v1; log the open order and take no new action.

Account and data handling:
- Robinhood MCP may expose all accounts and account numbers. Do not print, store, or email account numbers or raw MCP JSON.
- Logs may include account type labels, ticker, side, quantity, notional, limit price, decision reason, and non-sensitive order status.
- Do not write tokens, profile private fields, transfer details, card details, bank information, or full account identifiers.

Failure behavior:
- If anything is unclear, do nothing.
- If a tool call fails, do nothing and append an error-safe decision record.
- If daily usage cannot be computed, assume the daily limit is exhausted.
- If the model is unsure whether an order is allowed, do nothing.

Aggressive-mode boundaries:
- The goal is to increase upside capture inside a small, dedicated Agentic Account, not to bypass risk rules.
- Aggressive mode may favor high-momentum AI, space, defense, nuclear/power, and infrastructure names after premarket screening.
- Aggressive mode does not allow leverage, options, shorts, averaging down, stale data, or off-allowlist trades.
- If market volatility, news quality, liquidity, or account data cannot be verified, reduce risk or do nothing.
