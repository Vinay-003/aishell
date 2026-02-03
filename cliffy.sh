#!/usr/bin/env bash

# Source this script to keep your parent shell's cwd in sync with Cliffy.
# Usage: source ./cliffy.sh

CLIFFY_CWD_FILE="${CLIFFY_CWD_FILE:-/tmp/cliffy_cwd.$$}"
export CLIFFY_CWD_FILE

python3 "$(dirname "$0")/ai_shell_integration.py"

if [ -f "$CLIFFY_CWD_FILE" ]; then
  cd "$(cat "$CLIFFY_CWD_FILE")" || return 1
  rm -f "$CLIFFY_CWD_FILE"
fi
