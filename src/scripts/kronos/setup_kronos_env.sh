#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KRONOS_REPO_URL="https://github.com/shiyu-coder/Kronos.git"
KRONOS_COMMIT_SHA="67b630e67f6a18c9e9be918d9b4337c960db1e9a"

err() {
  printf '%s\n' "$*" >&2
}

resolve_repo_root() {
  local current="$SCRIPT_DIR"

  while [[ "$current" != "/" ]]; do
    if [[ -f "$current/requirements-kronos-extra.txt" && -d "$current/src/config" ]]; then
      printf '%s\n' "$current"
      return 0
    fi
    current="$(cd "$current/.." && pwd)"
  done

  return 1
}

REPO_ROOT="$(resolve_repo_root)" || {
  err "Unable to resolve repository root from $SCRIPT_DIR."
  err "Expected to find requirements-kronos-extra.txt and src/config."
  exit 1
}
VENV_DIR="$REPO_ROOT/.venv-kronos"
VENDOR_DIR="$REPO_ROOT/.vendor"
KRONOS_DIR="$VENDOR_DIR/kronos"
LOCAL_ENV_EXAMPLE="$REPO_ROOT/src/config/runtime.env.local.example"
LOCAL_ENV_FILE="$REPO_ROOT/src/config/runtime.env.local"

resolve_python_command() {
  local candidate="$1"

  if [[ "$candidate" == */* ]]; then
    [[ -x "$candidate" ]] || return 1
    printf '%s\n' "$candidate"
    return 0
  fi

  command -v "$candidate" 2>/dev/null
}

python_minor_version() {
  local python_bin="$1"
  "$python_bin" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")' 2>/dev/null
}

is_supported_bootstrap_version() {
  local version="$1"
  [[ "$version" == "3.11" || "$version" == "3.12" ]]
}

choose_bootstrap_python() {
  local resolved=""
  local version=""
  local candidate=""
  local -a unsupported=()
  local -a candidates=(python3.12 python3.11 python3)

  if [[ -n "${KRONOS_BOOTSTRAP_PYTHON:-}" ]]; then
    resolved="$(resolve_python_command "$KRONOS_BOOTSTRAP_PYTHON")" || {
      err "KRONOS_BOOTSTRAP_PYTHON=$KRONOS_BOOTSTRAP_PYTHON was not found or is not executable."
      exit 1
    }
    version="$(python_minor_version "$resolved")" || {
      err "Unable to determine Python version for KRONOS_BOOTSTRAP_PYTHON=$resolved."
      exit 1
    }
    if ! is_supported_bootstrap_version "$version"; then
      err "KRONOS_BOOTSTRAP_PYTHON=$resolved uses Python $version."
      err "Kronos setup requires Python 3.11 or 3.12 for upstream pandas==2.2.2 compatibility."
      err "Install python3.12 or python3.11, then rerun ./src/scripts/kronos/setup_kronos_env.sh."
      exit 1
    fi

    printf '%s\n' "$resolved"
    return 0
  fi

  for candidate in "${candidates[@]}"; do
    resolved="$(resolve_python_command "$candidate")" || continue
    version="$(python_minor_version "$resolved")" || continue
    if is_supported_bootstrap_version "$version"; then
      printf '%s\n' "$resolved"
      return 0
    fi
    unsupported+=("$resolved (Python $version)")
  done

  err "No compatible bootstrap Python found for Kronos setup."
  if [[ ${#unsupported[@]} -gt 0 ]]; then
    err "Unsupported interpreters discovered: ${unsupported[*]}"
  fi
  err "Install python3.12 or python3.11, or set KRONOS_BOOTSTRAP_PYTHON to a compatible interpreter path."
  exit 1
}

write_local_env_overrides() {
  local tmp_file
  tmp_file="$(mktemp)"

  trap 'rm -f "$tmp_file"' RETURN

  while IFS= read -r raw_line || [[ -n "$raw_line" ]]; do
    case "$raw_line" in
      KRONOS_PYTHON_BIN=*|KRONOS_PROJECT_ROOT=*)
        continue
        ;;
      *)
        printf '%s\n' "$raw_line" >> "$tmp_file"
        ;;
    esac
  done < "$LOCAL_ENV_FILE"

  printf 'KRONOS_PYTHON_BIN=%s\n' "$VENV_DIR/bin/python" >> "$tmp_file"
  printf 'KRONOS_PROJECT_ROOT=%s\n' "$KRONOS_DIR" >> "$tmp_file"
  mv "$tmp_file" "$LOCAL_ENV_FILE"
}

command -v git >/dev/null 2>&1 || { err "missing git"; exit 1; }

BOOTSTRAP_PYTHON="$(choose_bootstrap_python)"
BOOTSTRAP_VERSION="$(python_minor_version "$BOOTSTRAP_PYTHON")"

mkdir -p "$VENDOR_DIR"

if [[ ! -d "$VENV_DIR" ]]; then
  "$BOOTSTRAP_PYTHON" -m venv "$VENV_DIR"
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  err "Kronos virtualenv is missing $VENV_DIR/bin/python."
  err "Remove $VENV_DIR and rerun ./src/scripts/kronos/setup_kronos_env.sh with Python 3.11 or 3.12."
  exit 1
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

write_local_env_overrides

echo "Using bootstrap Python: $BOOTSTRAP_PYTHON (Python $BOOTSTRAP_VERSION)"
echo "Kronos portable environment ready."
echo "Next: ./src/scripts/kronos/verify_kronos_env.sh"
