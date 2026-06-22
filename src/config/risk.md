# Risk Rules

Live trading is allowed only inside the dedicated Robinhood Agentic Account.
Do not place orders in the user's ordinary Investing account, Roth IRA, Managed account, Spending account, Traditional IRA, crypto account, or any external account.

> Path note: file references below use the runtime-block variable names (e.g. `TODAY_ALLOWLIST_PATH`,
> `DAILY_PLAN_PATH`) that the premarket runtime block injects. They resolve at run time to the dated
> run folder `runtime/state/runs/<date>/planner|signals/...` — do not assume the old flat
> `runtime/state/<file>` paths.

Runtime modes:
- `paper`: never call `review_equity_order` or `place_equity_order`; write `would_trade` only.
- `review`: `review_equity_order` is allowed, but `place_equity_order` is forbidden.
- `live`: `place_equity_order` is allowed after every hard limit passes. Do not call `review_equity_order` by default in live mode; use it only when `REQUIRE_ROBINHOOD_REVIEW=1` is explicitly set or the broker/tool requires review.

Risk tiers:
- `RISK_TIER=0`: max single order `$10`, max daily notional `$25`, max 1 live order/day. This is the initial micro-test tier.
- `RISK_TIER=1`: max single order `$25`, max daily notional `$75`, max 2 live orders/day. Use only after at least 5 clean paper/review sessions.
- `RISK_TIER=2`: max single order `$50`, max daily notional `$150`, max 3 live orders/day. Use only after live tier 1 logs show no rule violations.
- `RISK_TIER=3`: max single order `$5,000`, max daily notional `$20,000`, max 4 live orders/day. Aggressive paper or small dedicated Agentic Account only.
- The premarket plan may set a lower daily cap than the tier cap, but must never exceed the tier cap.
- Any tier increase must be made manually in `src/config/runtime.env`; Codex must not raise `RISK_TIER` by itself.

Hard limits:
- Only trade symbols that are present in all applicable gates:
  - `src/config/universe.txt`;
  - `TODAY_ALLOWLIST_PATH`;
  - `DAILY_PLAN_PATH (today_watchlist field)`.
- `src/config/allowlist.txt` is only a static emergency fallback and must not be used for normal dynamic trading.
- Only long equities or ETFs.
- Never trade options, crypto, futures, margin, short selling, leveraged ETFs, or inverse ETFs.
- Buy orders may use dollar-based market orders during regular hours when the target is a dollar amount or fractional shares are required. This is the preferred live order shape for small high-priced-stock buys because Robinhood rejects fractional-share limit quantities.
- Limit orders remain allowed for whole-share buys and quantity-based sells when the policy plan supplies a valid limit price.
- Max single order notional is the lower of `src/config/runtime.env`, `RISK_TIER`, and `DAILY_PLAN_PATH`.
- Max daily notional is the lower of `src/config/runtime.env`, `RISK_TIER`, and `DAILY_PLAN_PATH`.
- Max one open order per symbol.
- Max one buy and one sell per symbol per day.
- Do not average down automatically if already holding a losing position.
- Do not trade if quote, account, position, order, or daily-usage data is missing, stale, or inconsistent.
- Do not trade if the dedicated Agentic Account cannot be identified unambiguously.
- Always call `get_equity_tradability` before a trade candidate.
- In `live`, place directly only after local gates, account checks, tradability checks, quote checks, and notional caps pass. If a direct placement fails or asks for review, do not improvise another order shape.
- In `review`, if review shows any warning, ambiguity, rejection, or unexpected field, do not place the order.
- If `market_regime` is `risk_off` or `no_trade`, do not place any order.
- If `KILL_SWITCH` exists, do not place any order.
- If `TODAY_ALLOWLIST_PATH` is missing, stale, empty, or not generated today, do not place any order.
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
