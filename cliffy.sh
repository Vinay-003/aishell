#!/usr/bin/env bash

# Source this script to keep your parent shell's cwd in sync with Cliffy.
# Usage: source ./cliffy.sh

_cliffy_run() {
  local script_dir cwd_file status final_cwd
  script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)" || return 1
  cwd_file="$(mktemp "${TMPDIR:-/tmp}/cliffy-cwd.XXXXXXXX")" || return 1
  # Pass a private handoff file only to the child; do not mutate caller config.
  if CLIFFY_CWD_FILE="$cwd_file" "${CLIFFY_PYTHON:-python3}" "$script_dir/cliffy_cli.py" "$@"; then
    status=0
    final_cwd="$(cat -- "$cwd_file")"
    if [[ -n "$final_cwd" ]]; then
      cd -- "$final_cwd" || status=1
    fi
  else
    status=$?
  fi
  rm -f -- "$cwd_file"
  return "$status"
}

if _cliffy_run "$@"; then
  unset -f _cliffy_run
  return 0 2>/dev/null || exit 0
else
  _cliffy_status=$?
  unset -f _cliffy_run
  return "$_cliffy_status" 2>/dev/null || exit "$_cliffy_status"
fi
