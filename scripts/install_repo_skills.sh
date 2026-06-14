#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_ROOT="$REPO_ROOT/.agents/skills"

if [[ ! -d "$SOURCE_ROOT" ]]; then
  echo "missing repo skill source: $SOURCE_ROOT" >&2
  exit 1
fi

if [[ -n "${REPO_SKILL_TARGETS:-}" ]]; then
  IFS=':' read -r -a TARGETS <<< "$REPO_SKILL_TARGETS"
else
  TARGETS=("$HOME/.agents/skills" "$HOME/.codex/skills")
fi

SKILLS=(
  chan-structure-trading
  brooks-trading-range-price-action
  equity-fundamentals-analysis
  trading-research-casebook-maintenance
)

for target in "${TARGETS[@]}"; do
  mkdir -p "$target"
  for skill in "${SKILLS[@]}"; do
    src="$SOURCE_ROOT/$skill"
    dst="$target/$skill"
    [[ -f "$src/SKILL.md" ]] || { echo "missing SKILL.md in $src" >&2; exit 1; }
    rm -rf "$dst"
    cp -R "$src" "$dst"
  done
done

echo "installed repo skills into ${TARGETS[*]}"
