# Source only in an interactive Bash 4+ session. Ctrl+G requests a draft;
# nothing runs until the user reviews the line and presses Enter themselves.
if [[ $- == *i* && ${BASH_VERSINFO[0]:-0} -ge 4 ]]; then
  _cliffy_generate_draft() {
    local original=${READLINE_LINE-} result status draft
    if [[ -z ${original//[[:space:]]/} ]]; then
      printf 'Cliffy: type a request first, then press Ctrl+G.\n' >&2
      return 0
    fi
    if [[ -z ${_cliffy_python-} || -z ${_cliffy_cli_module_dir-} ]]; then
      printf 'Cliffy: draft helper is unavailable; original text retained.\n' >&2
      return 0
    fi

    # Preserve source imports after the user changes directory. Credentials
    # remain in the inherited environment, never serialized into argv.
    # A sentinel retains trailing newlines that command substitution normally
    # removes. The exit code is kept separate from the untrusted stdout.
    result=$(PYTHONPATH="${_cliffy_cli_module_dir}${PYTHONPATH:+:$PYTHONPATH}" "$_cliffy_python" -m cliffy_cli --draft "$original"; status=$?; printf '\034%s' "$status")
    status=${result##*$'\034'}
    draft=${result%$'\034'*}
    # The CLI's one terminal LF frames the draft; any additional LF is unsafe.
    [[ $draft == *$'\n' ]] && draft=${draft%$'\n'}
    if [[ $status != 0 || -z $draft || ${#draft} -gt 8192 || $draft == *[$'\001'-$'\037'$'\177']* ]]; then
      printf 'Cliffy: no safe draft available; original text retained.\n' >&2
      return 0
    fi
    READLINE_LINE=$draft
    READLINE_POINT=${#READLINE_LINE}
    printf 'Cliffy: review the draft, then press Enter to run it (or edit/cancel).\n' >&2
  }

  # No editing-mode switch: each map is configured explicitly. An existing
  # Ctrl+G binding in either map is replaced only when the user sources this.
  bind -m emacs-standard -x '"\C-g":_cliffy_generate_draft'
  bind -m vi-insert -x '"\C-g":_cliffy_generate_draft'
fi
