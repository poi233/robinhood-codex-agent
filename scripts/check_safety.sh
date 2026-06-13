#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/common.sh
source "$SCRIPT_DIR/common.sh"

echo "Agent root: $AGENT_ROOT"
echo "Trading mode: $TRADING_MODE"
echo "Risk tier: $RISK_TIER"
echo "Kill switch: $(kill_switch_status)"
echo "Static fallback allowlist:"
rg -v '^\s*(#|$)' "$AGENT_ROOT/config/allowlist.txt" | sed 's/^/  - /'
echo "Universe count: $(rg -v '^\s*(#|$)' "$AGENT_ROOT/config/universe.txt" | wc -l | tr -d ' ')"

echo
echo "Safety checks:"

PROJECT_CODEX_CONFIG="$AGENT_ROOT/.codex/config.toml"
PREMARKET_SCRIPT="$AGENT_ROOT/scripts/run_premarket.sh"
READ_APPROVED_TOOLS=(
  get_accounts
  get_portfolio
  get_equity_positions
  get_option_positions
  get_equity_orders
  get_option_orders
  get_equity_quotes
  get_option_quotes
  get_index_quotes
  get_equity_historicals
  get_equity_tradability
  get_indexes
  search
  get_watchlists
  get_watchlist_items
  get_popular_watchlists
  get_option_watchlist
  get_option_chains
  get_option_instruments
)
PROMPT_GATED_TOOLS=(
  review_option_order
  place_equity_order
  place_option_order
  cancel_equity_order
  cancel_option_order
  add_to_watchlist
  remove_from_watchlist
  follow_watchlist
  unfollow_watchlist
  create_watchlist
  update_watchlist
  add_option_to_watchlist
  remove_option_from_watchlist
)

if [[ "$TRADING_MODE" == "live" ]]; then
  echo "  - TRADING_MODE is live. Confirm KILL_SWITCH is intentionally removed only after review rollout."
else
  echo "  - TRADING_MODE is not live: ok"
fi

case "$RISK_TIER" in
  0|1|2|3) echo "  - RISK_TIER is valid: ok" ;;
  *) echo "  - WARNING: RISK_TIER must be 0, 1, 2, or 3." ;;
esac

if [[ "$(kill_switch_status)" == "present" ]]; then
  echo "  - KILL_SWITCH present: intraday script will skip before Codex."
else
  echo "  - KILL_SWITCH absent: intraday script may run according to TRADING_MODE."
fi

if [[ -f "$PROJECT_CODEX_CONFIG" ]]; then
  echo "  - Project Codex config found: ok"
else
  echo "  - WARNING: project Codex config missing: $PROJECT_CODEX_CONFIG"
fi

missing_read_approvals=0
for tool in "${READ_APPROVED_TOOLS[@]}"; do
  if ! rg -q "mcp_servers\\.robinhood-trading\\.tools\\.$tool" "$PROJECT_CODEX_CONFIG" \
    || ! awk "/tools\\.$tool\\]/{seen=1; next} /^\\[/{seen=0} seen && /approval_mode = \"approve\"/{found=1} END{exit found ? 0 : 1}" "$PROJECT_CODEX_CONFIG"; then
    echo "  - WARNING: read tool is not auto-approved: $tool"
    missing_read_approvals=$((missing_read_approvals + 1))
  fi
done
if [[ "$missing_read_approvals" -eq 0 ]]; then
  echo "  - Robinhood read tools auto-approved in project config: ok"
fi

if awk '/tools\.review_equity_order\]/{seen=1; next} /^\[/{seen=0} seen && /approval_mode = "approve"/{found=1} END{exit found ? 0 : 1}' "$PROJECT_CODEX_CONFIG"; then
  echo "  - Equity order review is auto-approved for review mode: ok"
else
  echo "  - WARNING: review_equity_order is not auto-approved; review mode will not work unattended."
fi

write_auto_approvals=0
for tool in "${PROMPT_GATED_TOOLS[@]}"; do
  if awk "/tools\\.$tool\\]/{seen=1; next} /^\\[/{seen=0} seen && /approval_mode = \"approve\"/{found=1} END{exit found ? 0 : 1}" "$PROJECT_CODEX_CONFIG"; then
    echo "  - WARNING: trading/write tool is auto-approved: $tool"
    write_auto_approvals=$((write_auto_approvals + 1))
  fi
done
if [[ "$write_auto_approvals" -eq 0 ]]; then
  echo "  - Trading/write tools are not auto-approved: ok"
fi

if rg -q 'Do not call .*place_equity_order' "$AGENT_ROOT/prompts/premarket_research.txt" \
  && rg -q 'Do not call .*place_equity_order' "$AGENT_ROOT/prompts/postmarket_summary.txt" \
  && rg -q 'never place, review, cancel, or modify orders' "$AGENT_ROOT/prompts/dsa_premarket_scan.txt"; then
  echo "  - Non-trading prompts explicitly forbid place_equity_order: ok"
else
  echo "  - WARNING: non-trading prompts do not explicitly forbid place_equity_order."
fi

if [[ -f "$AGENT_ROOT/config/dsa_strategy_weights.json" ]] \
  && [[ -f "$AGENT_ROOT/prompts/dsa_premarket_scan.txt" ]] \
  && rg -q 'state/dsa_signals.json' "$AGENT_ROOT/prompts/premarket_research.txt" \
  && rg -q 'state/dsa_signals.json' "$AGENT_ROOT/prompts/intraday_check.txt"; then
  echo "  - DSA signal layer is configured and wired into premarket/intraday: ok"
else
  echo "  - WARNING: DSA signal layer is incomplete or not wired into prompts."
fi

if [[ -f "$AGENT_ROOT/scripts/kronos_generate_signals.py" ]] \
  && [[ -f "$AGENT_ROOT/scripts/run_kronos_premarket_scan.sh" ]] \
  && [[ -f "$PREMARKET_SCRIPT" ]] \
  && rg -q 'ENABLE_KRONOS_SIGNAL_LAYER' "$PREMARKET_SCRIPT" \
  && rg -q 'run_kronos_premarket_scan\.sh' "$PREMARKET_SCRIPT" \
  && rg -q 'state/kronos_signals.json' "$AGENT_ROOT/prompts/premarket_research.txt"; then
  echo "  - Kronos signal layer is configured and wired into premarket: ok"
else
  echo "  - WARNING: Kronos signal layer is incomplete or not wired into premarket."
fi

if [[ -f "$AGENT_ROOT/config/runtime.env.local.example" ]] \
  && [[ -f "$AGENT_ROOT/requirements-kronos-extra.txt" ]] \
  && [[ -f "$AGENT_ROOT/scripts/setup_kronos_env.sh" ]] \
  && [[ -f "$AGENT_ROOT/scripts/verify_kronos_env.sh" ]] \
  && rg -q '^ENABLE_KRONOS_SIGNAL_LAYER=' "$AGENT_ROOT/config/runtime.env"; then
  echo "  - Portable Kronos setup files found: ok"
else
  echo "  - WARNING: portable Kronos setup files missing."
fi

if rg -q 'Runtime mode behavior' "$AGENT_ROOT/prompts/intraday_check.txt"; then
  echo "  - Intraday prompt has runtime mode gate: ok"
else
  echo "  - WARNING: intraday prompt missing runtime mode gate."
fi

if rg -q 'Only use limit orders' "$AGENT_ROOT/config/risk.md"; then
  echo "  - Limit-order-only rule found: ok"
else
  echo "  - WARNING: limit-order-only rule missing."
fi
