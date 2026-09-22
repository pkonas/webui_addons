#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
DISPATCHER="$HERE/install-vut-ai-tutor-universal-v2.3.4.py"
if [[ ! -f "$DISPATCHER" ]]; then
  printf '[FAIL] Required package file is missing: %s\n' "$DISPATCHER" >&2
  exit 2
fi
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  printf '[FAIL] Python executable was not found: %s\n' "$PYTHON_BIN" >&2
  exit 2
fi
exec "$PYTHON_BIN" "$DISPATCHER" "$@"
