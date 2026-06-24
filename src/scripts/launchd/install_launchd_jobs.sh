#!/usr/bin/env bash

# Render and (re)load the launchd jobs for this checkout.
#
# Portable by design: REPO_ROOT is derived from this script's own location, so the generated
# plists point at wherever you cloned the repo — no hand-editing of __REPO_ROOT__, no pinned
# codex version, no user home baked in. Re-run it any time (e.g. after moving the checkout) to
# refresh the installed jobs.
#
# Usage:
#   src/scripts/launchd/install_launchd_jobs.sh            # render + load all jobs
#   src/scripts/launchd/install_launchd_jobs.sh install    # same as above
#   src/scripts/launchd/install_launchd_jobs.sh uninstall  # unload + remove installed plists
#   src/scripts/launchd/install_launchd_jobs.sh render      # only render to LaunchAgents, do not load
#
# Env overrides:
#   LAUNCH_AGENTS_DIR   target dir for plists       (default: ~/Library/LaunchAgents)
#   LAUNCHD_JOBS        space-separated job names   (default: all five)
#                       valid: premarket intraday postmarket nightly-analysis weekly-screen

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
TEMPLATE_DIR="$REPO_ROOT/launchd"
LAUNCH_AGENTS_DIR="${LAUNCH_AGENTS_DIR:-$HOME/Library/LaunchAgents}"

DEFAULT_JOBS="premarket intraday postmarket nightly-analysis weekly-screen"
read -r -a JOBS <<< "${LAUNCHD_JOBS:-$DEFAULT_JOBS}"

ACTION="${1:-install}"

die() { echo "error: $*" >&2; exit 1; }

template_for() { printf '%s/robinhood-codex-agent.%s.plist.example' "$TEMPLATE_DIR" "$1"; }

# Read the <key>Label</key><string>...</string> value from a plist file.
# Portable across BSD (macOS) and GNU sed: on the Label key line, advance to the
# next line and extract the text between <string>...</string>.
label_for() {
  local template="$1"
  sed -n '/<key>Label<\/key>/{n;s/.*<string>\(.*\)<\/string>.*/\1/p;}' "$template" | head -n1
}

active_strategy() {
  local registry="$REPO_ROOT/src/config/strategy_registry.yaml"
  if [[ ! -f "$registry" ]]; then
    printf 'baseline_v1\n'
    return
  fi
  sed -n 's/^active_strategy:[[:space:]]*//p' "$registry" | head -n1
}

interval_dict() {
  local hour="$1" minute="$2"
  printf '    <dict><key>Hour</key><integer>%s</integer><key>Minute</key><integer>%s</integer></dict>\n' "$hour" "$minute"
}

weekday_interval_dict() {
  local weekday="$1" hour="$2" minute="$3"
  printf '    <dict><key>Weekday</key><integer>%s</integer><key>Hour</key><integer>%s</integer><key>Minute</key><integer>%s</integer></dict>\n' "$weekday" "$hour" "$minute"
}

postmarket_start_minutes() {
  local template hour minute
  template="$(template_for postmarket)"
  hour="$(sed -n '/<key>Hour<\/key>/{n;s/.*<integer>\([0-9][0-9]*\)<\/integer>.*/\1/p;}' "$template" | head -n1)"
  minute="$(sed -n '/<key>Minute<\/key>/{n;s/.*<integer>\([0-9][0-9]*\)<\/integer>.*/\1/p;}' "$template" | head -n1)"
  [[ -n "$hour" && -n "$minute" ]] || die "could not read postmarket StartCalendarInterval from $template"
  printf '%s\n' $((10#$hour * 60 + 10#$minute))
}

nightly_analysis_schedule_xml() {
  local start total hour minute weekday
  start="$(postmarket_start_minutes)"
  total=$(((start + 30) % 1440))
  hour=$((total / 60))
  minute=$((total % 60))
  for weekday in 1 2 3 4 5; do
    weekday_interval_dict "$weekday" "$hour" "$minute"
  done
}

intraday_schedule_xml() {
  local strategy
  strategy="$(active_strategy)"
  case "$strategy" in
    baseline_v1)
      interval_dict 6 45
      for hour in 7 8 9 10 11 12; do
        interval_dict "$hour" 15
        interval_dict "$hour" 45
      done
      ;;
    midfreq_v1)
      interval_dict 6 45
      interval_dict 6 50
      interval_dict 6 55
      for hour in 7 8 9 10 11 12; do
        for minute in 0 5 10 15 20 25 30 35 40 45 50 55; do
          interval_dict "$hour" "$minute"
        done
      done
      ;;
    highfreq_v1)
      for minute in 45 46 47 48 49 50 51 52 53 54 55 56 57 58 59; do
        interval_dict 6 "$minute"
      done
      for hour in 7 8 9 10 11 12; do
        for minute in $(seq 0 59); do
          interval_dict "$hour" "$minute"
        done
      done
      ;;
    *)
      die "unknown active_strategy '$strategy' in src/config/strategy_registry.yaml; cannot render intraday schedule"
      ;;
  esac
}

render_one() {
  local job="$1" template label dest
  template="$(template_for "$job")"
  [[ -f "$template" ]] || die "no template for job '$job': $template"
  label="$(label_for "$template")"
  [[ -n "$label" ]] || die "could not read Label from $template"
  dest="$LAUNCH_AGENTS_DIR/$label.plist"

  # Escape & and | so they survive sed replacement of an arbitrary path.
  local escaped_root
  escaped_root="$(printf '%s' "$REPO_ROOT" | sed -e 's/[&|]/\\&/g')"
  if [[ "$job" == "intraday" || "$job" == "nightly-analysis" ]]; then
    local schedule_file
    schedule_file="$(mktemp)"
    if [[ "$job" == "intraday" ]]; then
      intraday_schedule_xml > "$schedule_file"
    else
      nightly_analysis_schedule_xml > "$schedule_file"
    fi
    sed "s|__REPO_ROOT__|$escaped_root|g" "$template" \
      | awk -v schedule_file="$schedule_file" '
          /__INTRADAY_SCHEDULE__/ || /__NIGHTLY_SCHEDULE__/ {
            while ((getline line < schedule_file) > 0) print line
            close(schedule_file)
            next
          }
          { print }
        ' \
      > "$dest"
    rm -f "$schedule_file"
  else
    sed "s|__REPO_ROOT__|$escaped_root|g" "$template" > "$dest"
  fi
  printf '%s\t%s\n' "$label" "$dest"
}

require_macos() {
  command -v launchctl >/dev/null 2>&1 || die "launchctl not found — this installer is for macOS launchd."
}

do_render() {
  mkdir -p "$LAUNCH_AGENTS_DIR" "$REPO_ROOT/runtime/logs"
  for job in "${JOBS[@]}"; do
    render_one "$job"
  done
}

do_install() {
  require_macos
  echo "Rendering ${#JOBS[@]} job(s) into $LAUNCH_AGENTS_DIR ..."
  local line label dest
  while IFS=$'\t' read -r label dest; do
    # Reload cleanly: unload any previous version (ignore "not loaded"), then load.
    launchctl unload "$dest" 2>/dev/null || true
    launchctl load -w "$dest"
    echo "loaded   $label"
  done < <(do_render)
  echo
  echo "Done. Verify with:  launchctl list | grep robinhood-codex-agent"
  echo "Logs:  $REPO_ROOT/runtime/logs/launchd.<job>.{out,err}"
  echo "Intraday schedule source: src/config/strategy_registry.yaml active_strategy=$(active_strategy)"
  echo "Nightly analysis schedule: postmarket + 30 minutes"
}

do_uninstall() {
  require_macos
  for job in "${JOBS[@]}"; do
    local template label dest
    template="$(template_for "$job")"
    [[ -f "$template" ]] || continue
    label="$(label_for "$template")"
    dest="$LAUNCH_AGENTS_DIR/$label.plist"
    if [[ -f "$dest" ]]; then
      launchctl unload "$dest" 2>/dev/null || true
      rm -f "$dest"
      echo "removed  $label"
    else
      echo "skip     $label (not installed)"
    fi
  done
}

case "$ACTION" in
  install)   do_install ;;
  uninstall) do_uninstall ;;
  render)
    do_render >/dev/null
    echo "Rendered ${#JOBS[@]} plist(s) into $LAUNCH_AGENTS_DIR (not loaded)."
    ;;
  *) die "unknown action '$ACTION' (use: install | uninstall | render)" ;;
esac
