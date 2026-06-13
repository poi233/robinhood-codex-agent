#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
KRONOS_REPO_URL="https://github.com/shiyu-coder/Kronos.git"
KRONOS_COMMIT_SHA="67b630e67f6a18c9e9be918d9b4337c960db1e9a"
VENV_DIR="$REPO_ROOT/.venv-kronos"
VENDOR_DIR="$REPO_ROOT/.vendor"
KRONOS_DIR="$VENDOR_DIR/kronos"
LOCAL_ENV_EXAMPLE="$REPO_ROOT/config/runtime.env.local.example"
LOCAL_ENV_FILE="$REPO_ROOT/config/runtime.env.local"

command -v git >/dev/null 2>&1 || { echo "missing git"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "missing python3"; exit 1; }

mkdir -p "$VENDOR_DIR"

if [[ ! -d "$VENV_DIR" ]]; then
  python3 -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install --upgrade pip

if [[ ! -d "$KRONOS_DIR/.git" ]]; then
  git clone "$KRONOS_REPO_URL" "$KRONOS_DIR"
fi

git -C "$KRONOS_DIR" fetch --all --tags
git -C "$KRONOS_DIR" checkout "$KRONOS_COMMIT_SHA"

"$VENV_DIR/bin/pip" install -r "$KRONOS_DIR/requirements.txt"
"$VENV_DIR/bin/pip" install -r "$REPO_ROOT/requirements-kronos-extra.txt"

if [[ ! -f "$LOCAL_ENV_FILE" ]]; then
  cp "$LOCAL_ENV_EXAMPLE" "$LOCAL_ENV_FILE"
fi

"$VENV_DIR/bin/python" - <<PY
from pathlib import Path
path = Path(r"$LOCAL_ENV_FILE")
lines = []
for raw in path.read_text(encoding="utf-8").splitlines():
    if raw.startswith("KRONOS_PYTHON_BIN=") or raw.startswith("KRONOS_PROJECT_ROOT="):
        continue
    lines.append(raw)
lines.append(f"KRONOS_PYTHON_BIN={Path(r'$VENV_DIR') / 'bin' / 'python'}")
lines.append(f"KRONOS_PROJECT_ROOT={Path(r'$KRONOS_DIR')}")
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

echo "Kronos portable environment ready."
echo "Next: ./scripts/verify_kronos_env.sh"
