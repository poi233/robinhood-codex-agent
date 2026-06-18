#!/usr/bin/env bash

# Guard against launchd-job regressions (the kind introduced by reverting the plists to call
# `python -m trading_agent <phase>` directly). For every launchd/*.plist.example this asserts the
# job is wired the portable way and prints PASS/FAIL per plist. Exits non-zero if any check fails.
#
# What it enforces, and why:
#   - ProgramArguments runs /bin/bash <entrypoint>.sh   → entry scripts cd to AGENT_ROOT, export the
#                                                          runtime env, and resolve python/codex. A
#                                                          bare `.venv/bin/python` skips all of that
#                                                          (this is what broke premarket's universe
#                                                          path resolution: /src/config/universe.txt).
#   - the entrypoint script actually exists             → no dangling reference.
#   - NOT `trading_agent nightly-analysis`              → there is no such CLI subcommand; the nightly
#                                                          batch only exists as run_nightly_analysis.sh.
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

  # 1) runs via /bin/bash
  check "$job: ProgramArguments should invoke /bin/bash" \
    grep -q "<string>/bin/bash</string>" "$template"

  # 2) invokes the matching entrypoint script, and that script exists
  entry_rel="src/scripts/entrypoints/run_${job//-/_}.sh"
  check "$job: should invoke $entry_rel" \
    grep -q "$entry_rel" "$template"
  check "$job: entrypoint $entry_rel must exist" \
    test -f "$REPO_ROOT/$entry_rel"

  # 3) must NOT call python -m trading_agent directly
  if grep -q ".venv/bin/python" "$template" || grep -q "<string>-m</string>" "$template"; then
    echo "  FAIL  $job: calls python -m trading_agent directly (bypasses entrypoint env/cwd setup)"
    fail=$((fail + 1))
  else
    pass=$((pass + 1))
  fi

  # 4) must NOT reference a non-existent CLI subcommand (nightly only exists as a shell script)
  check "$job: must not use the non-existent 'nightly-analysis' CLI subcommand" \
    bash -c "! grep -q '<string>nightly-analysis</string>' '$template'"

  # 5) no version-pinned codex release dir / hardcoded user home
  check "$job: no version-pinned codex release path" \
    bash -c "! grep -Eq 'standalone/releases/[0-9]' '$template'"
  check "$job: no hardcoded /Users/<name> home path" \
    bash -c "! grep -q '/Users/' '$template'"
done

echo ""
echo "=== launchd plist check: $pass passed, $fail failed ==="
[[ "$fail" -eq 0 ]]
