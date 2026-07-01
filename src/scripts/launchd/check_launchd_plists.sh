#!/usr/bin/env bash

# Guard against launchd-job regressions. For every launchd/*.plist.example this asserts the job is
# wired through the Python package entrypoint and prints PASS/FAIL per plist. Exits non-zero if any
# check fails.
#
# What it enforces, and why:
#   - ProgramArguments runs a rendered Python executable -m trading_agent <job>
#       → launchd on macOS can reject repo-local shell wrappers and stdout/stderr files under
#         Documents with "Operation not permitted"; direct Python plus a safe log dir avoids that
#         TCC/provenance failure while AGENT_ROOT and cwd keep runtime path resolution stable.
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
  subcommand="$job"
  [[ "$job" == "weekly-screen" ]] && subcommand="screen"
  body="$(cat "$template")"
  echo "[$job]"

  check "$job: ProgramArguments should invoke rendered python executable" \
    grep -q "<string>__PYTHON_BIN__</string>" "$template"
  check "$job: should call python -m trading_agent" \
    bash -c "grep -q '<string>-m</string>' '$template' && grep -q '<string>trading_agent</string>' '$template'"
  check "$job: should pass subcommand $job" \
    grep -q "<string>$subcommand</string>" "$template"
  check "$job: PATH should include repo .venv/bin first" \
    grep -q "<string>__REPO_ROOT__/.venv/bin:" "$template"
  check "$job: launchd stdout should use safe log dir placeholder" \
    grep -q "<string>__LAUNCHD_LOG_DIR__/launchd\\.$job\\.out</string>" "$template"
  check "$job: launchd stderr should use safe log dir placeholder" \
    grep -q "<string>__LAUNCHD_LOG_DIR__/launchd\\.$job\\.err</string>" "$template"

  # Verify the CLI parser knows this subcommand without running the job.
  python_bin="${LAUNCHD_PYTHON_BIN:-$REPO_ROOT/.venv/bin/python}"
  if PYTHONPATH="$REPO_ROOT/src" "$python_bin" -m trading_agent "$subcommand" --help >/dev/null 2>&1; then
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
