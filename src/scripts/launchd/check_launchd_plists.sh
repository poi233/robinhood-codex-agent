#!/usr/bin/env bash

# Guard against launchd-job regressions. For every launchd/*.plist.example this asserts the job is
# wired through the Python package entrypoint and prints PASS/FAIL per plist. Exits non-zero if any
# check fails.
#
# What it enforces, and why:
#   - ProgramArguments runs .venv/bin/python -m trading_agent <job>
#       → launchd on macOS can reject repo-local shell wrappers under Documents with "Operation not
#         permitted"; direct Python avoids that TCC/provenance failure while AGENT_ROOT and cwd keep
#         runtime path resolution stable.
#   - the matching Python CLI subcommand exists.
#   - no version-pinned codex release dir / user home   → those paths vanish on codex auto-update.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
TEMPLATE_DIR="$REPO_ROOT/launchd"

fail=0
pass=0

check() {  # check "<message>" <test-expr...>  — record PASS/FAIL, never abort
  local label="$1"; shift
  if "$@"; then
    pass=$((pass + 1))
  else
    echo "  FAIL  $label"
    fail=$((fail + 1))
  fi
}

shopt -s nullglob
templates=("$TEMPLATE_DIR"/*.plist.example)
if [[ "${#templates[@]}" -eq 0 ]]; then
  echo "no launchd/*.plist.example templates found in $TEMPLATE_DIR" >&2
  exit 1
fi

for template in "${templates[@]}"; do
  name="$(basename "$template")"
  # job = the token between "robinhood-codex-agent." and ".plist.example"
  job="${name#robinhood-codex-agent.}"
  job="${job%.plist.example}"
  body="$(cat "$template")"
  echo "[$job]"

  check "$job: ProgramArguments should invoke repo .venv python" \
    grep -q "<string>__REPO_ROOT__/.venv/bin/python</string>" "$template"
  check "$job: should call python -m trading_agent" \
    bash -c "grep -q '<string>-m</string>' '$template' && grep -q '<string>trading_agent</string>' '$template'"
  check "$job: should pass subcommand $job" \
    grep -q "<string>$job</string>" "$template"
  check "$job: PATH should include repo .venv/bin first" \
    grep -q "<string>__REPO_ROOT__/.venv/bin:" "$template"

  # Verify the CLI parser knows this subcommand without running the job.
  if PYTHONPATH="$REPO_ROOT/src" "$REPO_ROOT/.venv/bin/python" -m trading_agent "$job" --help >/dev/null 2>&1; then
    pass=$((pass + 1))
  else
    echo "  FAIL  $job: python -m trading_agent $job --help failed"
    fail=$((fail + 1))
  fi

  # no version-pinned codex release dir / hardcoded user home
  check "$job: no version-pinned codex release path" \
    bash -c "! grep -Eq 'standalone/releases/[0-9]' '$template'"
  check "$job: no hardcoded /Users/<name> home path" \
    bash -c "! grep -q '/Users/' '$template'"
done

echo ""
echo "=== launchd plist check: $pass passed, $fail failed ==="
[[ "$fail" -eq 0 ]]
