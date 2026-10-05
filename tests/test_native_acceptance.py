"""Public acceptance gates for an opt-in real Bash session."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_native_flags_are_documented_in_help():
    result = subprocess.run([sys.executable, str(ROOT / 'cliffy_cli.py'), '--help'],
                            capture_output=True, text=True, check=True)
    assert '--shell' in result.stdout
    assert '--shell-init' in result.stdout
    assert '--draft' in result.stdout


def test_native_session_refuses_nonterminal_input_without_executing_it(tmp_path):
    marker = tmp_path / 'must-not-exist'
    result = subprocess.run([sys.executable, str(ROOT / 'cliffy_cli.py'), '--shell', 'bash'],
                            input=f'touch {marker}\n', capture_output=True, text=True)
    assert result.returncode == 1
    assert 'terminal' in result.stderr.lower()
    assert not marker.exists()


def test_shell_init_is_only_a_plugin_not_an_execution_wrapper():
    result = subprocess.run([sys.executable, str(ROOT / 'cliffy_cli.py'), '--shell-init', 'bash'],
                            capture_output=True, text=True)
    assert result.returncode == 0
    assert 'READLINE_LINE' in result.stdout
    assert 'bind -x' in result.stdout
    assert 'eval ' not in result.stdout
    assert 'PROMPT_COMMAND=' not in result.stdout


def test_disabled_draft_does_not_start_interactive_runtime():
    result = subprocess.run([sys.executable, str(ROOT / 'cliffy_cli.py'),
                             '--no-ai', '--draft', 'show current directory'],
                            capture_output=True, text=True)
    assert result.returncode == 1
    assert not result.stdout
    assert 'disabled' in result.stderr.lower()
