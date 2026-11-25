#!/usr/bin/env bash
# Zero-dependency launcher for preflight.py.
# Locates any Python >= 3.8 (PATH -> WorkBuddy bundled runtimes) and execs it.
# Usage: bash bootstrap.sh <check|prepare|paths> [--json] [--ascii] [--workspace DIR] [...]
# Pass --ascii when stdout must be pure ASCII (PowerShell 5.1 / GBK consoles).
set -u

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
preflight="$script_dir/preflight.py"

py_ok() {
  "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' >/dev/null 2>&1
}

find_python() {
  local c p
  for c in python python3 py; do
    if command -v "$c" >/dev/null 2>&1 && py_ok "$c"; then
      command -v "$c"
      return 0
    fi
  done
  local wb="${WORKBUDDY_CONFIG_DIR:-$HOME/.workbuddy}"
  local res="${WORKBUDDY_RESOURCES_PATH:-}"
  for p in \
    "$res/vendor/python/python.exe" \
    "$res/vendor/python/python" \
    "$wb"/binaries/python/versions/*/python.exe \
    "$wb"/binaries/python/versions/*/python; do
    if [ -x "$p" ] && py_ok "$p"; then
      printf '%s\n' "$p"
      return 0
    fi
  done
  return 1
}

py="$(find_python)" || {
  printf '%s\n' '{"ok":false,"error":"python_not_found","hint":"Install Python 3.8+ or see references/environment.md section 8"}'
  exit 1
}

exec "$py" "$preflight" "$@"
