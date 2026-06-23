#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=src/scripts/lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

file_has_pattern() {
  local pattern="$1"
  local file="$2"
  grep -Eq -- "$pattern" "$file"
}

print_non_comment_lines() {
  local file="$1"
  awk '!/^[[:space:]]*(#|$)/ {print "  - " $0}' "$file"
}

count_non_comment_lines() {
  local file="$1"
  awk '!/^[[:space:]]*(#|$)/ {count++} END {print count + 0}' "$file"
}

echo "Agent root: $AGENT_ROOT"
echo "Trading mode: $TRADING_MODE"
echo "Risk tier: $RISK_TIER"
echo "Kill switch: $(kill_switch_status)"
echo "Static fallback allowlist:"
print_non_comment_lines "$SRC_ROOT/config/allowlist.txt"
echo "Universe count: $(count_non_comment_lines "$SRC_ROOT/config/universe.txt")"

echo
echo "Safety checks:"

PROJECT_CODEX_CONFIG="$AGENT_ROOT/.codex/config.toml"
PREMARKET_SCRIPT="$SRC_ROOT/scripts/entrypoints/run_premarket.sh"
PREMARKET_PIPELINE="$AGENT_ROOT/src/trading_agent/orchestration/premarket.py"
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
  if [[ "$TRADING_MODE" == "paper" ]]; then
    echo "  - KILL_SWITCH present: paper intraday may still run; live/review remain blocked."
  else
    echo "  - KILL_SWITCH present: intraday script will skip before Codex."
  fi
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
  if ! file_has_pattern "mcp_servers\\.robinhood-trading\\.tools\\.$tool" "$PROJECT_CODEX_CONFIG" \
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

if file_has_pattern 'Do not call .*place_equity_order' "$SRC_ROOT/prompts/premarket/final_research.txt" \
  && file_has_pattern 'Do not call .*place_equity_order' "$SRC_ROOT/prompts/postmarket/summary.txt" \
  && file_has_pattern 'never place, review, cancel, or modify orders' "$SRC_ROOT/prompts/signals/dsa_scan.txt"; then
  echo "  - Non-trading prompts explicitly forbid place_equity_order: ok"
else
  echo "  - WARNING: non-trading prompts do not explicitly forbid place_equity_order."
fi

if [[ -f "$SRC_ROOT/config/dsa_strategy_weights.json" ]] \
  && [[ -f "$SRC_ROOT/prompts/signals/dsa_scan.txt" ]] \
  && file_has_pattern 'DSA_SIGNALS_PATH' "$SRC_ROOT/prompts/premarket/final_research.txt" \
  && file_has_pattern 'DSA_SIGNALS_PATH' "$SRC_ROOT/prompts/intraday/check.txt"; then
  echo "  - DSA signal layer is configured and wired into premarket/intraday: ok"
else
  echo "  - WARNING: DSA signal layer is incomplete or not wired into prompts."
fi

if [[ -f "$SRC_ROOT/scripts/kronos/kronos_generate_signals.py" ]] \
  && [[ -f "$PREMARKET_PIPELINE" ]] \
  && [[ -f "$PREMARKET_SCRIPT" ]] \
  && file_has_pattern '-m trading_agent premarket' "$PREMARKET_SCRIPT" \
  && file_has_pattern 'def run_kronos' "$PREMARKET_PIPELINE" \
  && file_has_pattern '_write_kronos_signals' "$PREMARKET_PIPELINE" \
  && file_has_pattern 'KRONOS_SIGNALS_PATH' "$SRC_ROOT/prompts/premarket/final_research.txt"; then
  echo "  - Kronos signal layer is configured and wired into premarket: ok"
else
  echo "  - WARNING: Kronos signal layer is incomplete or not wired into premarket."
fi

if [[ -f "$SRC_ROOT/prompts/technical/research.txt" ]] \
  && [[ -f "$PREMARKET_PIPELINE" ]] \
  && [[ -f "$PREMARKET_SCRIPT" ]] \
  && file_has_pattern '-m trading_agent premarket' "$PREMARKET_SCRIPT" \
  && file_has_pattern 'collect_market_context' "$PREMARKET_PIPELINE" \
  && file_has_pattern 'technical.*research\.txt' "$PREMARKET_PIPELINE" \
  && file_has_pattern 'TECHNICAL_SIGNALS_PATH' "$SRC_ROOT/prompts/premarket/final_research.txt" \
  && file_has_pattern 'TECHNICAL_SIGNALS_PATH' "$SRC_ROOT/prompts/intraday/check.txt"; then
  echo "  - Technical signal layer is configured and wired into premarket/intraday: ok"
else
  echo "  - WARNING: technical signal layer is incomplete or not wired into prompts."
fi

if [[ -f "$SRC_ROOT/config/runtime.env.local.example" ]] \
  && [[ -f "$AGENT_ROOT/requirements-kronos-extra.txt" ]] \
  && [[ -f "$SRC_ROOT/scripts/kronos/setup_kronos_env.sh" ]] \
  && [[ -f "$SRC_ROOT/scripts/kronos/verify_kronos_env.sh" ]] \
  && file_has_pattern '^KRONOS_MODEL_NAME=' "$SRC_ROOT/config/runtime.env"; then
  echo "  - Portable Kronos setup files found: ok"
else
  echo "  - WARNING: portable Kronos setup files missing."
fi

if file_has_pattern 'Runtime mode behavior' "$SRC_ROOT/prompts/intraday/check.txt"; then
  echo "  - Intraday prompt has runtime mode gate: ok"
else
  echo "  - WARNING: intraday prompt missing runtime mode gate."
fi

if file_has_pattern 'dollar-based market orders' "$SRC_ROOT/config/risk.md" \
  && file_has_pattern 'Robinhood rejects fractional-share limit quantities' "$SRC_ROOT/config/risk.md"; then
  echo "  - Dollar-amount market-buy rule found: ok"
else
  echo "  - WARNING: dollar-amount market-buy rule missing."
fi
