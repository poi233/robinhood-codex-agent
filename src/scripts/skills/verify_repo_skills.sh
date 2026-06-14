#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SOURCE_ROOT="$REPO_ROOT/.agents/skills"
SKILLS=(
  chan-structure-trading
  brooks-trading-range-price-action
  equity-fundamentals-analysis
  trading-research-casebook-maintenance
)

TARGETS=("$HOME/.agents/skills" "$HOME/.codex/skills")
status=0

for target in "${TARGETS[@]}"; do
  echo "checking $target"
  for skill in "${SKILLS[@]}"; do
    dst="$target/$skill"
    if [[ ! -f "$dst/SKILL.md" ]]; then
      echo "missing $dst/SKILL.md" >&2
      status=1
      continue
    fi
    if [[ -d "$SOURCE_ROOT/$skill/references" && ! -d "$dst/references" ]]; then
      echo "missing $dst/references" >&2
      status=1
    fi
    if [[ -d "$SOURCE_ROOT/$skill/casebook" && ! -d "$dst/casebook" ]]; then
      echo "missing $dst/casebook" >&2
      status=1
    fi
  done
done

exit "$status"
