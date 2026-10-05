"""Opt-in Bash launcher and one-shot command drafting."""
from __future__ import annotations

import importlib.resources
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import tempfile


def shell_init() -> str:
    plugin = importlib.resources.files('cliffy_shell').joinpath('bash.sh').read_text(encoding='utf-8')
    module_dir = str(Path(__file__).resolve().parent)
    return ('# bind -x integration is installed by the bundled Bash plugin.\n'
            f'_cliffy_python={shlex.quote(sys.executable)}\n'
            f'_cliffy_cli_module_dir={shlex.quote(module_dir)}\n' + plugin + '\n')


def launch_bash() -> int:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print('Native Bash requires an input and output terminal.', file=sys.stderr)
        return 1
    try:
        with tempfile.TemporaryDirectory(prefix='cliffy-bash-') as directory:
            rc = Path(directory) / 'bashrc'
            user_rc = Path.home() / '.bashrc'
            # The user's configuration runs first; plugin bindings take precedence.
            rc.write_text('if (( BASH_VERSINFO[0] < 4 )); then '
                          "printf 'Cliffy native integration requires Bash 4+.\\n' >&2; exit 1; fi\n"
                          + f'if [[ -f {shlex.quote(str(user_rc))} ]]; then source {shlex.quote(str(user_rc))}; fi\n'
                          + shell_init(), encoding='utf-8')
            rc.chmod(0o600)
            # Spawn before ignoring signals: exec preserves SIG_IGN, which would
            # make Bash's foreground programs unable to respond to Ctrl+C.
            child = subprocess.Popen(['bash', '--noprofile', '--rcfile', str(rc), '-i'])
            old_int = signal.signal(signal.SIGINT, signal.SIG_IGN)
            old_quit = signal.signal(signal.SIGQUIT, signal.SIG_IGN)
            try:
                try:
                    return child.wait()
                except KeyboardInterrupt:
                    return child.wait()
            finally:
                signal.signal(signal.SIGINT, old_int)
                signal.signal(signal.SIGQUIT, old_quit)
    except (OSError, ImportError) as exc:
        print('Native Bash could not start; check Bash and package installation.', file=sys.stderr)
        return 1


_FENCE = re.compile(r'\A```(?:bash|sh)?\n([^\r\n]+)\n```\Z', re.IGNORECASE)
_PROSE = re.compile(r'^(?:here(?: is|\'s)|sure|command:|run |you can |to |the command)', re.IGNORECASE)


def _command(value: str) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip(' ')
    fence = _FENCE.fullmatch(value)
    if value.startswith('```'):
        if not fence:
            return None
        value = fence.group(1)
    if (not value or len(value) > 8192 or _PROSE.match(value) or any(ord(char) < 32 or ord(char) == 127 for char in value)
            or value.endswith(('\\', '|', '&&', '||', ';'))):
        return None
    return value


def draft(task: str) -> int:
    if os.getenv('CLIFFY_NO_AI', '').strip().lower() in ('1', 'true', 'yes', 'on'):
        print('AI drafting is disabled.', file=sys.stderr)
        return 1
    if not task or not task.strip() or any(ord(c) < 32 for c in task):
        print('Draft task must be a single nonempty line.', file=sys.stderr)
        return 1
    try:
        from cliffy_providers import AIClient, ProviderConfig, ProviderError
        client = AIClient(ProviderConfig.from_env())
        response = client.complete(
            f'Task: {task}\nCurrent directory: {os.getcwd()}\nReturn exactly one Bash command on one line.',
            system='Translate the task into exactly one single-line Bash command. No explanation, no markdown, no execution.',
            max_tokens=256)
        command = _command(response)
        if command is None:
            print('AI response was not a single valid command.', file=sys.stderr)
            return 1
        print(command)
        return 0
    except ProviderError:
        print('AI drafting unavailable; check provider configuration or connectivity.', file=sys.stderr)
        return 1
    except (OSError, ValueError):
        print('AI drafting failed.', file=sys.stderr)
        return 1
