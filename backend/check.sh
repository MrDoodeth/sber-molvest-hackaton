#!/usr/bin/env bash

set -euo pipefail

BACKEND_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$BACKEND_DIR/.venv"

if [[ ! -x "$VENV_DIR/bin/ruff" || ! -x "$VENV_DIR/bin/python" ]]; then
  printf 'Static analysis tools are missing. Create backend/.venv and install the dev dependencies.\n' >&2
  exit 1
fi

printf 'Running Ruff lint...\n'
"$VENV_DIR/bin/ruff" check \
  --config "$BACKEND_DIR/pyproject.toml" \
  "$BACKEND_DIR/app"

printf '\nChecking Ruff formatting...\n'
"$VENV_DIR/bin/ruff" format --check \
  --config "$BACKEND_DIR/pyproject.toml" \
  "$BACKEND_DIR/app"

printf '\nRunning Mypy...\n'
MYPYPATH="$BACKEND_DIR" "$VENV_DIR/bin/python" -m mypy \
  --config-file "$BACKEND_DIR/pyproject.toml" \
  "$BACKEND_DIR/app"

printf '\nBackend checks passed.\n'
