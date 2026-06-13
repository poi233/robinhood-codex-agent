#!/usr/bin/env bash

set -euo pipefail

AGENT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_ENV="$AGENT_ROOT/config/runtime.env"
RUN_LOG="$AGENT_ROOT/logs/codex_runs.log"
ERROR_LOG="$AGENT_ROOT/logs/errors.log"
DECISIONS_LOG="$AGENT_ROOT/logs/decisions.jsonl"
ORDERS_LOG="$AGENT_ROOT/logs/orders.jsonl"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

mkdir -p "$AGENT_ROOT/logs" "$AGENT_ROOT/state"
: >> "$RUN_LOG"
: >> "$ERROR_LOG"
: >> "$DECISIONS_LOG"
: >> "$ORDERS_LOG"

OVERRIDE_TRADING_MODE="${TRADING_MODE-}"
OVERRIDE_CODEX_MODEL="${CODEX_MODEL-}"
OVERRIDE_CODEX_BIN="${CODEX_BIN-}"
OVERRIDE_RISK_TIER="${RISK_TIER-}"
OVERRIDE_MAX_SINGLE_ORDER_NOTIONAL="${MAX_SINGLE_ORDER_NOTIONAL-}"
OVERRIDE_MAX_DAILY_NOTIONAL="${MAX_DAILY_NOTIONAL-}"
OVERRIDE_CODEX_EXEC_TIMEOUT_SEC="${CODEX_EXEC_TIMEOUT_SEC-}"
OVERRIDE_ENABLE_DSA_SIGNAL_LAYER="${ENABLE_DSA_SIGNAL_LAYER-}"

if [[ -f "$CONFIG_ENV" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$CONFIG_ENV"
  set +a
fi

[[ -n "$OVERRIDE_TRADING_MODE" ]] && TRADING_MODE="$OVERRIDE_TRADING_MODE"
[[ -n "$OVERRIDE_CODEX_MODEL" ]] && CODEX_MODEL="$OVERRIDE_CODEX_MODEL"
[[ -n "$OVERRIDE_CODEX_BIN" ]] && CODEX_BIN="$OVERRIDE_CODEX_BIN"
[[ -n "$OVERRIDE_RISK_TIER" ]] && RISK_TIER="$OVERRIDE_RISK_TIER"
[[ -n "$OVERRIDE_MAX_SINGLE_ORDER_NOTIONAL" ]] && MAX_SINGLE_ORDER_NOTIONAL="$OVERRIDE_MAX_SINGLE_ORDER_NOTIONAL"
[[ -n "$OVERRIDE_MAX_DAILY_NOTIONAL" ]] && MAX_DAILY_NOTIONAL="$OVERRIDE_MAX_DAILY_NOTIONAL"
[[ -n "$OVERRIDE_CODEX_EXEC_TIMEOUT_SEC" ]] && CODEX_EXEC_TIMEOUT_SEC="$OVERRIDE_CODEX_EXEC_TIMEOUT_SEC"
[[ -n "$OVERRIDE_ENABLE_DSA_SIGNAL_LAYER" ]] && ENABLE_DSA_SIGNAL_LAYER="$OVERRIDE_ENABLE_DSA_SIGNAL_LAYER"

TRADING_MODE="${TRADING_MODE:-paper}"
CODEX_MODEL="${CODEX_MODEL:-gpt-5.5}"
CODEX_BIN="${CODEX_BIN:-codex}"
RISK_TIER="${RISK_TIER:-0}"
MAX_SINGLE_ORDER_NOTIONAL="${MAX_SINGLE_ORDER_NOTIONAL:-10}"
MAX_DAILY_NOTIONAL="${MAX_DAILY_NOTIONAL:-25}"
CODEX_EXEC_TIMEOUT_SEC="${CODEX_EXEC_TIMEOUT_SEC:-600}"
ENABLE_DSA_SIGNAL_LAYER="${ENABLE_DSA_SIGNAL_LAYER:-1}"

pt_now() {
  TZ=America/Los_Angeles date '+%Y-%m-%dT%H:%M:%S%z'
}

pt_date() {
  TZ=America/Los_Angeles date '+%Y-%m-%d'
}

log_line() {
  printf '%s %s\n' "$(pt_now)" "$*" >> "$RUN_LOG"
}

kill_switch_status() {
  if [[ -f "$AGENT_ROOT/KILL_SWITCH" ]]; then
    printf 'present'
  else
    printf 'absent'
  fi
}

is_weekday_pt() {
  local weekday
  weekday="$(TZ=America/Los_Angeles date '+%w')"
  [[ "$weekday" -ge 1 && "$weekday" -le 5 ]]
}

is_intraday_window_pt() {
  local hour minute current start end
  hour="$(TZ=America/Los_Angeles date '+%H')"
  minute="$(TZ=America/Los_Angeles date '+%M')"
  current=$((10#$hour * 60 + 10#$minute))
  start=$((6 * 60 + 45))
  end=$((12 * 60 + 55))
  [[ "$current" -ge "$start" && "$current" -le "$end" ]]
}

append_local_decision() {
  local run_kind="$1"
  local decision="$2"
  local reason="$3"
  printf '{"timestamp":"%s","run_kind":"%s","trading_mode":"%s","decision":"%s","action_taken":"none","reason":"%s"}\n' \
    "$(pt_now)" "$run_kind" "$TRADING_MODE" "$decision" "$reason" >> "$DECISIONS_LOG"
}

acquire_lock() {
  local name="$1"
  local lock_dir="$AGENT_ROOT/state/${name}.lock"
  if ! mkdir "$lock_dir" 2>/dev/null; then
    log_line "$name lock exists, skipping run."
    exit 0
  fi
  trap "rmdir '$lock_dir' 2>/dev/null || true" EXIT
}

build_runtime_block() {
  local run_kind="$1"
  cat <<RUNTIME
<runtime>
RUN_KIND=$run_kind
RUN_STARTED_AT=$(pt_now)
RUN_DATE_PT=$(pt_date)
TIMEZONE=America/Los_Angeles
AGENT_ROOT=$AGENT_ROOT
TRADING_MODE=$TRADING_MODE
RISK_TIER=$RISK_TIER
KILL_SWITCH_STATUS=$(kill_switch_status)
ALLOW_OUTSIDE_MARKET_TEST=${ALLOW_OUTSIDE_MARKET_TEST:-0}
MAX_SINGLE_ORDER_NOTIONAL=$MAX_SINGLE_ORDER_NOTIONAL
MAX_DAILY_NOTIONAL=$MAX_DAILY_NOTIONAL
CODEX_EXEC_DRY_RUN=${CODEX_EXEC_DRY_RUN:-0}
ENABLE_DSA_SIGNAL_LAYER=$ENABLE_DSA_SIGNAL_LAYER
</runtime>

RUNTIME
}

run_codex_prompt() {
  local run_kind="$1"
  local prompt_file="$2"

  if [[ ! -f "$prompt_file" ]]; then
    log_line "$run_kind prompt file missing: $prompt_file"
    printf '%s missing prompt file: %s\n' "$(pt_now)" "$prompt_file" >> "$ERROR_LOG"
    return 1
  fi

  log_line "$run_kind starting mode=$TRADING_MODE model=$CODEX_MODEL kill_switch=$(kill_switch_status)"

  if [[ "${CODEX_EXEC_DRY_RUN:-0}" == "1" ]]; then
    log_line "$run_kind CODEX_EXEC_DRY_RUN=1, not invoking codex exec."
    printf '%s DRY_RUN %s mode=%s kill_switch=%s prompt=%s\n' \
      "$(pt_now)" "$run_kind" "$TRADING_MODE" "$(kill_switch_status)" "$prompt_file" >> "$RUN_LOG"
    return 0
  fi

  if ! command -v "$CODEX_BIN" >/dev/null 2>&1; then
    log_line "$run_kind failed: CODEX_BIN not found: $CODEX_BIN"
    printf '%s CODEX_BIN not found: %s\n' "$(pt_now)" "$CODEX_BIN" >> "$ERROR_LOG"
    return 127
  fi

  local prompt_input
  prompt_input="$(mktemp "${TMPDIR:-/tmp}/robinhood-codex-${run_kind}.XXXXXX")"
  {
    build_runtime_block "$run_kind"
    cat "$prompt_file"
  } > "$prompt_input"

  set +e
  "$CODEX_BIN" --ask-for-approval never exec \
    --cd "$AGENT_ROOT" \
    --skip-git-repo-check \
    --sandbox workspace-write \
    -m "$CODEX_MODEL" \
    - < "$prompt_input" >> "$RUN_LOG" 2>> "$ERROR_LOG" &
  local codex_pid=$!
  (
    sleep "$CODEX_EXEC_TIMEOUT_SEC"
    if kill -0 "$codex_pid" 2>/dev/null; then
      printf '%s %s codex exec timeout after %ss\n' "$(pt_now)" "$run_kind" "$CODEX_EXEC_TIMEOUT_SEC" >> "$ERROR_LOG"
      kill -TERM "$codex_pid" 2>/dev/null || true
      sleep 5
      kill -KILL "$codex_pid" 2>/dev/null || true
    fi
  ) &
  local watchdog_pid=$!

  wait "$codex_pid"
  local status=$?
  kill "$watchdog_pid" 2>/dev/null || true
  wait "$watchdog_pid" 2>/dev/null || true
  rm -f "$prompt_input"
  set -e

  if [[ "$status" -ne 0 ]]; then
    log_line "$run_kind failed status=$status"
    return "$status"
  fi

  log_line "$run_kind completed status=0"
}
