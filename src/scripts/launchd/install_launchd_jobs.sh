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
#   LAUNCHD_JOBS        space-separated job names   (default: all four)
#                       valid: premarket intraday postmarket nightly-analysis

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
TEMPLATE_DIR="$REPO_ROOT/launchd"
LAUNCH_AGENTS_DIR="${LAUNCH_AGENTS_DIR:-$HOME/Library/LaunchAgents}"

DEFAULT_JOBS="premarket intraday postmarket nightly-analysis"
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
  sed "s|__REPO_ROOT__|$escaped_root|g" "$template" > "$dest"
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
